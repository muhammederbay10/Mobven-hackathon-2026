"""Contract tests against the AI engineer's delivered fixtures.

Phase 0 shared architecture step 5: "Add backend/frontend contract tests that
load the AI engineer's delivered fixtures without network access."

These tests are a *defect detector*, not an implementation. Plan section 8.8:
"If an assertion fails, the full-stack agent records the request/response
contract defect and hands it to the AI engineer. It must not patch files under
``ai/``."

Until the H4 deliverables land (GAP-10) the fixture-driven tests skip with an
explicit hand-off message. Those skips are a schedule signal — after H4 a skip
here means a missed deliverable, not a passing suite.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from api import schemas as s
from api.tests.conftest import (
    AI_FIXTURES_DIR,
    CASES_FILE,
    DATA_DIR,
    EXTRACTION_FIXTURES_DIR,
    REGISTRY_SEED_FILE,
    REPORT_FIXTURES_DIR,
    collect_json,
    load_json,
    require_delivered,
)

# Nothing in this module opens a socket; every input is a committed local file.

REP_SOURCE_ID_CONVENTION = re.compile(r"^rep-\d+$")
UNMASKED_TCKN = re.compile(r"(?<!\d)\d{11}(?!\d)")


def _extractions() -> list[tuple[str, object]]:
    payloads = collect_json(AI_FIXTURES_DIR, EXTRACTION_FIXTURES_DIR)
    return [
        (label, body)
        for label, body in payloads
        if isinstance(body, dict) and "representatives" in body
    ]


def _reports() -> list[tuple[str, object]]:
    payloads = collect_json(AI_FIXTURES_DIR, REPORT_FIXTURES_DIR)
    return [
        (label, body) for label, body in payloads if isinstance(body, dict) and "checks" in body
    ]


# ---------------------------------------------------------------------------
# ExtractionResult deliverables
# ---------------------------------------------------------------------------


def test_delivered_extractions_validate_against_the_frozen_schema() -> None:
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")

    defects: list[str] = []
    for label, body in found:
        try:
            s.ExtractionResult.model_validate(body)
        except ValidationError as exc:
            defects.append(f"{label}: {exc}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_non_null_legal_facts_carry_verbatim_evidence() -> None:
    """Plan sections 5.1 and 8.8.4: a non-null legal fact needs a real quote."""
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")

    defects: list[str] = []
    for label, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        facts: list[tuple[str, s.Fact]] = [
            ("company.legal_name", extraction.company.legal_name),
            ("company.tax_number", extraction.company.tax_number),
            ("company.mersis", extraction.company.mersis),
            ("company.trade_registry_number", extraction.company.trade_registry_number),
            ("notary.name", extraction.notary.name),
            ("notary.date", extraction.notary.date),
            ("notary.journal_number", extraction.notary.journal_number),
            ("document_valid_until", extraction.document_valid_until),
        ]
        for rep in extraction.representatives:
            for attr in ("name", "tckn_masked", "title", "degree", "authority_mode"):
                facts.append((f"representatives[{rep.source_id}].{attr}", getattr(rep, attr)))

        for path, fact in facts:
            if fact.value is None:
                continue
            if not fact.evidence:
                defects.append(f"{label}: {path} has a value but no evidence")
                continue
            for ref in fact.evidence:
                if not ref.quote.strip():
                    defects.append(f"{label}: {path} evidence quote is empty")
                if ref.page > extraction.page_count:
                    defects.append(
                        f"{label}: {path} cites page {ref.page} of {extraction.page_count}"
                    )
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_unreadable_values_are_null_plus_a_review_flag() -> None:
    """Plan section 5.1: the model must not guess. Null needs a flag."""
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")

    defects: list[str] = []
    for label, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        flagged = {flag.field_path for flag in extraction.fields_needing_review}
        for path, fact in (
            ("company.legal_name", extraction.company.legal_name),
            ("company.tax_number", extraction.company.tax_number),
            ("company.mersis", extraction.company.mersis),
            ("document_valid_until", extraction.document_valid_until),
        ):
            if fact.value is None and not any(path in f for f in flagged):
                defects.append(f"{label}: {path} is null with no entry in fields_needing_review")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_every_rule_signer_reference_resolves() -> None:
    """Plan section 8.8.3: a representative reference is never silently dropped."""
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")

    defects: list[str] = []
    for label, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        known = {rep.source_id for rep in extraction.representatives}
        flagged = " ".join(f.field_path + f.message for f in extraction.fields_needing_review)
        for rule in extraction.rules:
            for signer in rule.required_signers:
                if signer not in known and signer not in flagged:
                    defects.append(f"{label}: rule {rule.id} requires unknown signer {signer}")
            if rule.minimum_signature_count > max(len(rule.required_signers), 1):
                defects.append(
                    f"{label}: rule {rule.id} needs {rule.minimum_signature_count} signatures "
                    f"but names {len(rule.required_signers)} signers"
                )
        for rep in extraction.representatives:
            for other in rep.joint_with_source_ids:
                if other not in known:
                    defects.append(f"{label}: {rep.source_id} is joint with unknown {other}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_amount_limits_are_ordered_integer_kurus() -> None:
    """GAP-12: integer minor units only; 500,000 TL is 50000000."""
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")

    defects: list[str] = []
    for label, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        for rule in extraction.rules:
            low, high = rule.min_amount_minor, rule.max_amount_minor
            for name, amount in (("min", low), ("max", high)):
                if amount is not None and isinstance(amount, bool):
                    defects.append(f"{label}: rule {rule.id} {name}_amount_minor is a bool")
            if low is not None and high is not None and low > high:
                defects.append(f"{label}: rule {rule.id} has min {low} above max {high}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_source_ids_follow_the_agreed_rep_n_convention() -> None:
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")

    defects = [
        f"{label}: source_id {rep.source_id!r} is not rep-N"
        for label, body in found
        for rep in s.ExtractionResult.model_validate(body).representatives
        if not REP_SOURCE_ID_CONVENTION.match(rep.source_id)
    ]
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


# ---------------------------------------------------------------------------
# CheckReport deliverables
# ---------------------------------------------------------------------------


def test_delivered_reports_validate_against_the_frozen_schema() -> None:
    found = _reports()
    require_delivered(found, "CheckReport fixtures")

    defects: list[str] = []
    for label, body in found:
        try:
            s.CheckReport.model_validate(body)
        except ValidationError as exc:
            defects.append(f"{label}: {exc}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_delivered_reports_agree_with_the_documented_precedence() -> None:
    """Defect detector for plan section 6.1 — NOT a second comparison engine.

    Section 6 forbids the bank API from re-deriving statuses or verdicts, and
    section 18 bans a second copy inside application, comparison,
    authority-building or transaction-enforcement services. A test is the one
    place the plan does allow this: it catches an inconsistent delivery so it can
    be handed back, and no runtime code path imports it.
    """
    found = _reports()
    require_delivered(found, "CheckReport fixtures")

    V = s.OnboardingVerdict
    defects: list[str] = []
    for label, body in found:
        report = s.CheckReport.model_validate(body)
        status = {c.id: c.status for c in report.checks}
        red = {cid for cid, st in status.items() if st is s.CheckStatus.RED}
        identity_group = set(s.CHECK_IDS[:5])
        registry_group = {"registry_company_status", "registry_representative_status"}

        if red & identity_group:
            allowed = {V.MISMATCH}
        elif red & registry_group:
            allowed = {V.REGISTRY_CONFLICT}
        elif red & {"authority_mode", "document_validity"}:
            allowed = {V.MISMATCH}
        elif status["authority_mode"] is s.CheckStatus.AMBER:
            allowed = {V.CO_SIGNER_REQUIRED}
        else:
            allowed = {V.READY}

        if report.verdict not in allowed:
            defects.append(
                f"{label}: verdict {report.verdict.value} but precedence allows "
                f"{sorted(v.value for v in allowed)} (red: {sorted(red) or 'none'})"
            )
        if red and set(report.blocking_check_ids) != red:
            defects.append(
                f"{label}: blocking_check_ids {sorted(report.blocking_check_ids)} "
                f"does not match the red checks {sorted(red)}"
            )
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


# ---------------------------------------------------------------------------
# Privacy — plan section 14 and GAP-08
# ---------------------------------------------------------------------------


def test_no_fixture_contains_a_plausible_unmasked_tckn() -> None:
    """Plan section 14: never store a plausible unmasked 11-digit TCKN."""
    found = _extractions() + _reports()
    require_delivered(found, "AI fixtures")

    defects: list[str] = []
    for label, body in found:
        for match in UNMASKED_TCKN.finditer(repr(body)):
            defects.append(f"{label}: contains an 11-digit run {match.group()!r}")
    assert not defects, "privacy defects to hand back:\n" + "\n".join(defects)


# ---------------------------------------------------------------------------
# Full-stack-owned demo data
# ---------------------------------------------------------------------------


def test_registry_seed_matches_the_fixed_cast() -> None:
    """Phase 0 data steps 2 and 10, GAP-08 and GAP-09."""
    registry = s.Registry.model_validate(load_json(REGISTRY_SEED_FILE))
    companies = {company.mersis: company for company in registry.companies}
    assert set(companies) == {"0123456789000017", "0987654321000023"}

    abc = companies["0123456789000017"]
    assert abc.legal_name == "ABC Teknoloji Ltd. Şti."
    assert abc.tax_number == "1234567890"
    assert {rep.id: (rep.name, rep.tckn) for rep in abc.representatives} == {
        "rep_abc_ali": ("Ali Yılmaz", "123******01"),
        "rep_abc_ayse": ("Ayşe Demir", "987******45"),
    }

    zeta = companies["0987654321000023"]
    assert zeta.legal_name == "Zeta İnşaat A.Ş."
    assert zeta.tax_number == "9876543210"
    assert {rep.id: (rep.name, rep.tckn) for rep in zeta.representatives} == {
        "rep_zeta_kemal": ("Kemal Öz", "555******22")
    }

    # The baseline is fully active: cases opt into deviations, never out of them.
    for company in registry.companies:
        assert company.status is s.RegistryCompanyStatus.ACTIVE
        for rep in company.representatives:
            assert rep.status is s.RegistryRepresentativeStatus.ACTIVE
            assert re.match(s.REGISTRY_REP_ID_PATTERN, rep.id)


def test_no_committed_demo_data_contains_an_unmasked_tckn() -> None:
    """Plan section 14 / GAP-08, applied to full-stack-owned fixtures."""
    defects: list[str] = []
    for path in (REGISTRY_SEED_FILE, CASES_FILE):
        for match in UNMASKED_TCKN.finditer(path.read_text(encoding="utf-8")):
            defects.append(f"{path.name}: contains an 11-digit run {match.group()!r}")
    assert not defects, "\n".join(defects)


def test_clean_case_fixture_is_act_two_capable() -> None:
    """Phase 0 data step 5, against the delivered case-1 extraction.

    Section 11.1: the clean fixture is deliberately Act-2 capable so the stage
    can connect branch approval to mobile enforcement — both signers and all
    four source-backed rules must be present. Section 1.4 and 8.8: these are
    *fixture* expectations checked in a test. No engine may branch on any of
    these names, limits or subjects.
    """
    case_one = [
        (label, body)
        for label, body in _extractions()
        if "case1" in label.replace("_", "").lower()
    ]
    require_delivered(case_one, "case 1 ExtractionResult fixture")

    _, body = case_one[0]
    extraction = s.ExtractionResult.model_validate(body)

    names = {rep.name.value for rep in extraction.representatives}
    assert {"Ali Yılmaz", "Ayşe Demir"} <= names, names

    by_subject: dict[s.TransactionSubject, list[s.AuthorityRule]] = {}
    for rule in extraction.rules:
        by_subject.setdefault(rule.subject, []).append(rule)

    # General: sole below the boundary, joint above it (500.000 TL = 50000000).
    general = by_subject.get(s.TransactionSubject.GENERAL, [])
    assert len(general) >= 2, "case 1 needs a sole and a joint general rule"
    sole = [r for r in general if r.allowed and r.minimum_signature_count == 1]
    joint = [r for r in general if r.allowed and r.minimum_signature_count >= 2]
    assert sole and joint
    assert any(rule.max_amount_minor == 50_000_000 for rule in sole), (
        "the 500.000 TL boundary must come from the fixture's rule data, "
        "never from a product constant"
    )

    # Credit: joint at any amount.
    credit = [r for r in by_subject.get(s.TransactionSubject.CREDIT, []) if r.allowed]
    assert credit and all(rule.minimum_signature_count >= 2 for rule in credit)

    # Real estate: present and explicitly not authorized, so the denial has a source.
    real_estate = by_subject.get(s.TransactionSubject.REAL_ESTATE, [])
    assert real_estate and not any(rule.allowed for rule in real_estate)


def test_case_documents_exist_once_rendered() -> None:
    """Phase 0 data step 4. Blocked on the AI engineer's H2 notarial text."""
    cases = load_json(CASES_FILE)
    assert isinstance(cases, dict)
    referenced = sorted({case["document"] for case in cases["cases"]})
    missing = [name for name in referenced if not (DATA_DIR / "documents" / name).is_file()]
    if missing:
        pytest.skip(
            f"Documents not rendered yet: {missing}. They need the AI engineer's "
            "notarial Turkish text (GAP-10, due H2), then "
            "`python scripts/render_documents.py` (due H4)."
        )
    for name in referenced:
        assert (DATA_DIR / "documents" / name).stat().st_size > 0
