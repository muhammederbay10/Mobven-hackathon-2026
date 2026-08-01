"""Demo case loading and reset — plan sections 8.2 and 1.4.

Task `P0-04` acceptance: "a reset from a clean checkout completes under two
seconds and produces identical row counts and registry JSON; loading each case
returns a persistent application ID."
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from api.config import Settings
from api.db import get_engine, session_scope
from api.models import Application, AuditAction, AuditLog
from api.schemas import ApplicationStatus, RegistryRepresentativeStatus
from api.services import demo_service, registry_service
from api.services.audit_service import new_correlation_id

CASE_NUMBERS = (1, 2, 3, 4)


def _load(settings: Settings, case_number: int) -> int:
    with session_scope() as session:
        return demo_service.load_case(
            session, case_number, correlation_id=new_correlation_id(), settings=settings
        )


def _registry_digest(settings: Settings) -> str:
    return hashlib.sha256(settings.registry_path.read_bytes()).hexdigest()


def _row_counts(settings: Settings) -> dict[str, int]:
    with Session(get_engine()) as session:
        return {
            "applications": len(session.exec(select(Application)).all()),
            "audit": len(session.exec(select(AuditLog)).all()),
        }


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_number", CASE_NUMBERS)
def test_loading_a_case_creates_a_persistent_application(
    demo_env: Settings, case_number: int
) -> None:
    application_id = _load(demo_env, case_number)

    # Persistent means: readable from a *different* session, after the loader
    # returned. A demo that loses the application on refresh is not a demo.
    with Session(get_engine()) as session:
        application = session.get(Application, application_id)
    assert application is not None
    assert application.id == application_id
    assert application.status is ApplicationStatus.IDENTITY_VERIFIED


def test_every_case_uses_the_fixed_fictional_cast(demo_env: Settings) -> None:
    """Phase 0 data step 10 / GAP-08."""
    cast = {
        "Ali Yılmaz": "123******01",
        "Ayşe Demir": "987******45",
        "Mehmet Kaya": "456******07",
        "Kemal Öz": "555******22",
    }
    companies = {
        "ABC Teknoloji Ltd. Şti.": ("1234567890", "0123456789000017"),
        "Zeta İnşaat A.Ş.": ("9876543210", "0987654321000023"),
    }
    for case in demo_service.load_cases(demo_env).cases:
        application = case.application
        assert application.applicant_name in cast, case.case
        assert cast[application.applicant_name] == application.applicant_tckn_masked
        assert application.company_name in companies, case.case
        assert companies[application.company_name] == (application.tax_number, application.mersis)


def test_expected_verdicts_match_section_11(demo_env: Settings) -> None:
    verdicts = {case.case: case.expected_verdict.value for case in demo_service.load_cases(demo_env).cases}
    assert verdicts == {
        1: "READY",
        2: "CO_SIGNER_REQUIRED",
        3: "MISMATCH",
        4: "REGISTRY_CONFLICT",
    }


def test_case_three_application_and_document_deliberately_disagree(demo_env: Settings) -> None:
    """Section 11: the application is ABC/Mehmet Kaya, the document is Zeta/Kemal Öz."""
    case = demo_service.get_case(3, demo_env)
    assert case.application.company_name == "ABC Teknoloji Ltd. Şti."
    assert case.application.applicant_name == "Mehmet Kaya"
    # The mismatch must come from the document, so the application itself stays
    # internally consistent — otherwise case 3 would fail for the wrong reason.
    assert case.application.mersis == "0123456789000017"


def test_unknown_case_number_is_a_controlled_error(demo_env: Settings) -> None:
    from api.errors import ApiError

    with pytest.raises(ApiError) as exc:
        demo_service.get_case(99, demo_env)
    assert exc.value.status_code == 404
    assert exc.value.code.value == "UNKNOWN_CASE"


# ---------------------------------------------------------------------------
# Registry patching and order independence
# ---------------------------------------------------------------------------


def test_case_four_removes_ali_from_the_runtime_registry(demo_env: Settings) -> None:
    _load(demo_env, 4)
    company = registry_service.get_company("0123456789000017", demo_env)
    assert company is not None
    ali = next(rep for rep in company.representatives if rep.id == "rep_abc_ali")
    assert ali.status is RegistryRepresentativeStatus.REMOVED


def test_case_four_never_writes_to_the_committed_seed(demo_env: Settings) -> None:
    """Phase 4: "loading case 4 applies its registry patch without affecting
    later reset baseline"."""
    before = demo_env.registry_seed_path.read_bytes()
    _load(demo_env, 4)
    assert demo_env.registry_seed_path.read_bytes() == before

    seed = registry_service.load_seed(demo_env)
    company = next(c for c in seed.companies if c.mersis == "0123456789000017")
    ali = next(rep for rep in company.representatives if rep.id == "rep_abc_ali")
    assert ali.status is RegistryRepresentativeStatus.ACTIVE


def test_case_loading_is_deterministic_in_any_order(demo_env: Settings) -> None:
    """Phase 4 backend step 3 and review step 1: run 1-2-3-4, then 4-1-3-2.

    Without restoring the baseline before applying a case's own patch, case 4
    would leave Ali removed and silently turn the clean case into a registry
    conflict on the next load — the single most demo-breaking form of drift.
    """
    # The property: registry state after loading case N depends only on N, never
    # on what ran before it.
    demo_service.reset_demo(demo_env)
    from_clean = {}
    for case_number in CASE_NUMBERS:
        demo_service.reset_demo(demo_env)
        _load(demo_env, case_number)
        from_clean[case_number] = _registry_digest(demo_env)

    for order in ((1, 2, 3, 4), (4, 1, 3, 2), (4, 4, 1), (2, 4, 3, 1)):
        demo_service.reset_demo(demo_env)
        for case_number in order:
            _load(demo_env, case_number)
            assert _registry_digest(demo_env) == from_clean[case_number], (order, case_number)

    # Concretely: the clean case really is clean again after case 4 ran before it.
    _load(demo_env, 4)
    _load(demo_env, 1)
    company = registry_service.get_company("0123456789000017", demo_env)
    assert company is not None
    assert all(rep.status is RegistryRepresentativeStatus.ACTIVE for rep in company.representatives)


# ---------------------------------------------------------------------------
# Reset — section 8.2
# ---------------------------------------------------------------------------


def test_reset_restores_identical_row_counts_and_registry(demo_env: Settings) -> None:
    demo_service.reset_demo(demo_env)
    baseline_counts = _row_counts(demo_env)
    baseline_registry = _registry_digest(demo_env)

    for case_number in CASE_NUMBERS:
        _load(demo_env, case_number)
    assert _row_counts(demo_env) != baseline_counts

    demo_service.reset_demo(demo_env)
    assert _row_counts(demo_env) == baseline_counts
    assert _registry_digest(demo_env) == baseline_registry


def test_reset_completes_in_under_two_seconds(demo_env: Settings) -> None:
    """P0-04 acceptance. Slow reset means a dead stage pause between takes."""
    for case_number in CASE_NUMBERS:
        _load(demo_env, case_number)

    started = time.perf_counter()
    demo_service.reset_demo(demo_env)
    assert time.perf_counter() - started < 2.0


def test_reset_clears_uploads(demo_env: Settings) -> None:
    upload = demo_env.uploads_path / "scan.pdf"
    upload.write_bytes(b"%PDF-1.4 fake")
    nested = demo_env.uploads_path / "pages" / "1"
    nested.mkdir(parents=True)
    (nested / "page-1.png").write_bytes(b"png")

    result = demo_service.reset_demo(demo_env)

    assert result["removed_uploads"] == 2
    assert not upload.exists()
    assert list(demo_env.uploads_path.iterdir()) == []


def test_reset_preserves_the_prewarmed_extraction_cache(demo_env: Settings) -> None:
    """GAP-11: cases 2-4 are pre-warmed during final rehearsal, and section 16
    has the presenter reset immediately before the judged run. A reset that
    wiped the cache would silently discard the stage policy."""
    cached = demo_env.cache_path / "abc__1-0__engine.json"
    cached.write_text("{}", encoding="utf-8")

    demo_service.reset_demo(demo_env)

    assert cached.is_file()


def test_reset_writes_an_audit_row(demo_env: Settings) -> None:
    demo_service.reset_demo(demo_env)
    with Session(get_engine()) as session:
        rows = session.exec(select(AuditLog)).all()
    assert [row.action for row in rows] == [AuditAction.DEMO_RESET]
    assert rows[0].actor == "branch_user:kozyatagi01"


# ---------------------------------------------------------------------------
# Reset blast radius — Phase 0 backend step 6
# ---------------------------------------------------------------------------


def test_clear_refuses_directories_outside_the_runtime_data_dir(
    demo_env: Settings, tmp_path: Path
) -> None:
    """Section 8.2: reset "must not delete files outside configured runtime
    directories"."""
    outsider = tmp_path / "not-mine"
    outsider.mkdir()
    (outsider / "precious.txt").write_text("keep me", encoding="utf-8")

    for forbidden in (outsider, demo_env.data_path, demo_env.documents_path, demo_env.fixtures_path):
        with pytest.raises(ValueError, match="not a configured runtime directory"):
            demo_service.clear_runtime_directory(forbidden, demo_env)

    assert (outsider / "precious.txt").is_file()


def test_reset_does_not_touch_committed_demo_input(demo_env: Settings) -> None:
    document = demo_env.documents_path / "case1.pdf"
    document.write_bytes(b"%PDF-1.4 committed")
    cases_before = demo_env.cases_path.read_bytes()

    demo_service.reset_demo(demo_env)

    assert document.read_bytes() == b"%PDF-1.4 committed"
    assert demo_env.cases_path.read_bytes() == cases_before
    assert demo_env.registry_seed_path.is_file()


def test_gitkeep_survives_a_reset(demo_env: Settings) -> None:
    """Otherwise the runtime directory disappears from a fresh clone."""
    keep = demo_env.uploads_path / ".gitkeep"
    keep.write_text("", encoding="utf-8")
    demo_service.reset_demo(demo_env)
    assert keep.is_file()
