"""Registry, audit and AI-client foundations.

Plan sections 8.4 (atomic registry writes), 14 (audit and redaction), 15 (fail
closed) and 4.3 / 8.8 (AI modes and the backend-owned cache key).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from sqlmodel import Session, select

from api.config import Settings
from api.db import get_engine, session_scope
from api.errors import invalid_state_transition
from api.models import Application, AuditAction, AuditEntity, AuditLog
from api.schemas import (
    SCHEMA_VERSION,
    ApplicationStatus,
    CreateApplicationRequest,
    RegistryRepresentativeStatus,
)
from api.services import ai_client, application_service, audit_service, registry_service

ABC = "0123456789000017"


# ---------------------------------------------------------------------------
# Registry — section 8.4, GAP-09, GAP-13
# ---------------------------------------------------------------------------


def test_registry_falls_back_to_the_seed_before_the_first_reset(demo_env: Settings) -> None:
    assert not demo_env.registry_path.exists()
    registry = registry_service.load(demo_env)
    assert {company.mersis for company in registry.companies} == {ABC, "0987654321000023"}


def test_representatives_are_addressed_by_stable_id_not_name(demo_env: Settings) -> None:
    """GAP-09: stable IDs address, normalized names match. Never the same job."""
    registry_service.set_representative_status(
        ABC, "rep_abc_ali", RegistryRepresentativeStatus.REMOVED, demo_env
    )
    company = registry_service.get_company(ABC, demo_env)
    assert company is not None
    assert {rep.id: rep.status.value for rep in company.representatives} == {
        "rep_abc_ali": "REMOVED",
        "rep_abc_ayse": "ACTIVE",
    }

    with pytest.raises(KeyError):
        registry_service.set_representative_status(
            ABC, "Ali Yılmaz", RegistryRepresentativeStatus.REMOVED, demo_env
        )


def test_unknown_company_or_representative_raises(demo_env: Settings) -> None:
    with pytest.raises(KeyError):
        registry_service.set_representative_status(
            "0000000000000000", "rep_abc_ali", RegistryRepresentativeStatus.REMOVED, demo_env
        )
    with pytest.raises(KeyError):
        registry_service.set_representative_status(
            ABC, "rep_abc_nobody", RegistryRepresentativeStatus.REMOVED, demo_env
        )


def test_registry_writes_leave_no_temp_files_behind(demo_env: Settings) -> None:
    registry_service.reset_to_seed(demo_env)
    strays = [p.name for p in demo_env.data_path.iterdir() if p.name.endswith(".tmp")]
    assert strays == []


def test_concurrent_registry_writes_do_not_lose_updates(demo_env: Settings) -> None:
    """Section 8.4: a process-level lock protects concurrent writes.

    Two threads flip two different representatives. Without the lock, one
    read-modify-write overwrites the other and a status change vanishes — on
    stage that looks like the registry screen simply ignoring a click.
    """
    registry_service.reset_to_seed(demo_env)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def flip(rep_id: str) -> None:
        try:
            barrier.wait(timeout=5)
            registry_service.set_representative_status(
                ABC, rep_id, RegistryRepresentativeStatus.REMOVED, demo_env
            )
        except BaseException as exc:  # pragma: no cover - only on a real race
            errors.append(exc)

    threads = [threading.Thread(target=flip, args=(rep,)) for rep in ("rep_abc_ali", "rep_abc_ayse")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    company = registry_service.get_company(ABC, demo_env)
    assert company is not None
    assert all(rep.status is RegistryRepresentativeStatus.REMOVED for rep in company.representatives)


def test_registry_read_failure_fails_closed(demo_env: Settings) -> None:
    """Section 15: a registry read failure must not look like 'no representatives'."""
    demo_env.registry_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(registry_service.RegistryUnavailableError):
        registry_service.load(demo_env)

    demo_env.registry_path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    registry_service.load(demo_env)  # companies defaults to [] — a valid, complete document

    demo_env.registry_path.write_text(
        json.dumps({"schema_version": "1.0", "companies": [{"mersis": "nope"}]}), encoding="utf-8"
    )
    with pytest.raises(registry_service.RegistryUnavailableError):
        registry_service.load(demo_env)


def test_registry_file_keeps_turkish_characters_readable(demo_env: Settings) -> None:
    registry_service.reset_to_seed(demo_env)
    raw = demo_env.registry_path.read_text(encoding="utf-8")
    assert "Ayşe Demir" in raw
    assert "Zeta İnşaat A.Ş." in raw
    assert "\\u" not in raw  # not escaped into unreadable JSON


# ---------------------------------------------------------------------------
# Audit — section 14 and 15
# ---------------------------------------------------------------------------


def test_audit_actor_is_the_fixed_branch_user(demo_env: Settings) -> None:
    with session_scope() as session:
        audit_service.record_branch_action(
            session,
            action=AuditAction.APPLICATION_CREATED,
            entity_type=AuditEntity.APPLICATION,
            entity_id=1,
            correlation_id="abc123",
        )
    with Session(get_engine()) as session:
        row = session.exec(select(AuditLog)).one()
    assert row.actor == "branch_user:kozyatagi01"
    assert row.correlation_id == "abc123"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("TCKN 12345678901 kaydedildi", "TCKN [REDACTED_TCKN] kaydedildi"),
        ("123******01", "123******01"),  # the masked form is what we keep
        ("1234567890", "1234567890"),  # a 10-digit VKN is not a TCKN
    ],
)
def test_redaction_removes_plausible_unmasked_tckns(value: str, expected: str) -> None:
    assert audit_service.redact(value) == expected


def test_redaction_reaches_into_nested_structures_and_drops_bytes() -> None:
    detail = {
        "people": [{"tckn": "98765432109"}],
        "scan": b"%PDF-1.4 binary",
        "note": "x" * 900,
    }
    cleaned = audit_service.redact(detail)
    assert cleaned["people"][0]["tckn"] == "[REDACTED_TCKN]"
    assert cleaned["scan"] == "<15 bytes omitted>"
    assert cleaned["note"].endswith("…[truncated]")
    assert len(cleaned["note"]) < 600


def test_a_failed_audit_write_rolls_back_the_business_action(demo_env: Settings) -> None:
    """Section 15: "Audit-write failure: roll back the material business action"."""
    request = CreateApplicationRequest(
        company_name="ABC Teknoloji Ltd. Şti.",
        tax_number="1234567890",
        mersis=ABC,
        applicant_name="Ali Yılmaz",
        applicant_tckn_masked="123******01",
        branch_code="kozyatagi01",
        identity_verified_at_branch=True,
    )
    with pytest.raises(RuntimeError, match="audit exploded"):
        with session_scope() as session:
            application_service.create_application(session, request, correlation_id="c1")
            raise RuntimeError("audit exploded")

    with Session(get_engine()) as session:
        assert session.exec(select(Application)).all() == []
        assert session.exec(select(AuditLog)).all() == []


# ---------------------------------------------------------------------------
# Application state — section 7.2
# ---------------------------------------------------------------------------


def test_identity_attestation_is_required_to_leave_draft(demo_env: Settings) -> None:
    """Section 8.3: identity attestation is required to reach IDENTITY_VERIFIED."""
    base = {
        "company_name": "ABC Teknoloji Ltd. Şti.",
        "tax_number": "1234567890",
        "mersis": ABC,
        "applicant_name": "Ali Yılmaz",
        "applicant_tckn_masked": "123******01",
        "branch_code": "kozyatagi01",
    }
    with session_scope() as session:
        without = application_service.create_application(
            session, CreateApplicationRequest(**base, identity_verified_at_branch=False), correlation_id="c1"
        )
        assert without.status is ApplicationStatus.DRAFT

        with_attestation = application_service.create_application(
            session, CreateApplicationRequest(**base, identity_verified_at_branch=True), correlation_id="c2"
        )
        assert with_attestation.status is ApplicationStatus.IDENTITY_VERIFIED


def test_invalid_transitions_return_409(demo_env: Settings) -> None:
    request = CreateApplicationRequest(
        company_name="ABC Teknoloji Ltd. Şti.",
        tax_number="1234567890",
        mersis=ABC,
        applicant_name="Ali Yılmaz",
        applicant_tckn_masked="123******01",
        branch_code="kozyatagi01",
        identity_verified_at_branch=True,
    )
    with session_scope() as session:
        application = application_service.create_application(session, request, correlation_id="c1")
        # IDENTITY_VERIFIED -> APPROVED skips scan, analysis and review entirely.
        with pytest.raises(type(invalid_state_transition("a", "b"))) as exc:
            application_service.transition(
                session, application, ApplicationStatus.APPROVED, correlation_id="c1"
            )
    assert exc.value.status_code == 409
    assert exc.value.code.value == "INVALID_STATE_TRANSITION"


# ---------------------------------------------------------------------------
# AI client foundations — sections 4.3 and 8.8
# ---------------------------------------------------------------------------


def test_cache_key_covers_hash_schema_and_engine() -> None:
    """Section 8.8: the key is (document_sha256, schema_version, engine)."""
    sha = "a" * 64
    base = ai_client.cache_key(sha, "1.0", "claude-opus-5")
    assert base == ai_client.cache_key(sha.upper(), "1.0", "Claude-Opus-5")
    # A contract bump or a model change must never serve the previous payload.
    assert base != ai_client.cache_key(sha, "1.1", "claude-opus-5")
    assert base != ai_client.cache_key(sha, "1.0", "gpt-oss")
    assert base != ai_client.cache_key("b" * 64, "1.0", "claude-opus-5")


def test_cache_key_is_filesystem_safe() -> None:
    key = ai_client.cache_key("f" * 64, SCHEMA_VERSION, "vendor/model:v2 (preview)")
    assert not set(key) & set('/\\:*?"<>| ')


def test_cache_paths_stay_inside_the_cache_directory(demo_env: Settings) -> None:
    from api.config import ConfigurationError

    cache = ai_client.ExtractionCache(demo_env)
    assert cache.directory == demo_env.cache_path
    with pytest.raises(ConfigurationError):
        cache.path_for("../../escaped")


def test_cache_is_a_no_op_when_switched_off(
    demo_env: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api import config

    monkeypatch.setenv("EXTRACTION_CACHE", "off")
    config.get_settings.cache_clear()
    try:
        cache = ai_client.ExtractionCache(config.get_settings())
        assert cache.enabled is False
        assert cache.get("a" * 64, "engine") is None
    finally:
        config.get_settings.cache_clear()


def test_corrupt_cache_entry_reads_as_a_miss(demo_env: Settings) -> None:
    """A bad file on disk means 'call the model again', not 'fail the demo'."""
    cache = ai_client.ExtractionCache(demo_env)
    sha = "c" * 64
    path = cache.path_for(ai_client.cache_key(sha, SCHEMA_VERSION, "engine"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    assert cache.get(sha, "engine") is None

    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    assert cache.get(sha, "engine") is None


def test_cache_clear_can_target_one_document(demo_env: Settings) -> None:
    """GAP-11: clear case 1 while cases 2-4 stay pre-warmed."""
    cache = ai_client.ExtractionCache(demo_env)
    keep, drop = "1" * 64, "2" * 64
    for sha in (keep, drop):
        target: Path = cache.path_for(ai_client.cache_key(sha, SCHEMA_VERSION, "engine"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

    assert cache.clear(drop) == 1
    assert cache.path_for(ai_client.cache_key(keep, SCHEMA_VERSION, "engine")).is_file()
    assert cache.clear() == 1


def test_describe_mode_hides_the_ai_url_and_local_paths(demo_env: Settings) -> None:
    described = ai_client.describe_mode(demo_env)
    assert described["ai_mode"] == "stub"
    assert described["ai_url"] is None
    assert described["extract_available"] is False
    assert described["extraction_cache"] == "on"
    assert described["cache_ready"] is True
    # Section 5.7: no local filesystem paths in an API response, readiness included.
    assert not any(isinstance(value, str) and Path(value).is_absolute() for value in described.values())
