"""Demo seeding, case loading and reset — plan sections 8.2 and 1.4.

This module is the **only** place in the backend that is allowed to know a case
number exists. Section 1.4: "Case numbers may appear only in demo routing,
fixture loading, and test names", and section 18 requires an agent to reject any
`if case_id == …` inside application, comparison, authority-building or
transaction-enforcement code. So the loader below does exactly what rule 7 of
section 1.4 describes: it creates ordinary domain records from fixture data and
then calls the same services a non-demo request would.

`expected_verdict` is carried through to the control-panel cards and the tests.
No engine reads it, and nothing here branches on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from api.config import Settings, get_settings, resolve_under
from api.db import drop_all, init_db, session_scope
from api.errors import unknown_case
from api.models import AuditAction, AuditEntity
from api.schemas import (
    CreateApplicationRequest,
    MersisStr,
    OnboardingVerdict,
    RegistryRepIdStr,
    RegistryRepresentativeStatus,
)
from api.services import application_service, audit_service, registry_service


class RegistryPatch(BaseModel):
    """A single deviation from the committed registry baseline."""

    model_config = ConfigDict(extra="forbid")

    mersis: MersisStr
    rep_id: RegistryRepIdStr
    status: RegistryRepresentativeStatus


class DemoCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: int = Field(ge=1)
    title: str
    description: str
    expected_verdict: OnboardingVerdict
    document: str
    application: CreateApplicationRequest
    registry_patch: list[RegistryPatch] = Field(default_factory=list)


class DemoCases(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    cases: list[DemoCase]
    # Free-form note block in the JSON file; carried so `extra="forbid"` still
    # catches genuine typos in the fixture.
    comment: list[str] = Field(default_factory=list, alias="_comment")


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def load_cases(settings: Settings | None = None) -> DemoCases:
    settings = settings or get_settings()
    raw = json.loads(settings.cases_path.read_text(encoding="utf-8"))
    return DemoCases.model_validate(raw)


def get_case(case_number: int, settings: Settings | None = None) -> DemoCase:
    for case in load_cases(settings).cases:
        if case.case == case_number:
            return case
    raise unknown_case(case_number)


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------


def load_case(
    session: Session,
    case_number: int,
    *,
    correlation_id: str,
    settings: Settings | None = None,
) -> int:
    """Load a demo case and return its persistent application ID.

    The registry is restored to the committed baseline and then the case's own
    patch is applied. That is what makes case loading "deterministic in any
    order" (Phase 4 backend step 3): without the restore, running 4 before 1
    would leave Ali removed and quietly turn the clean case into a registry
    conflict. Only the runtime registry is touched — the seed is never written,
    so the reset baseline stays intact.
    """
    settings = settings or get_settings()
    case = get_case(case_number, settings)

    registry_service.reset_to_seed(settings)
    for patch in case.registry_patch:
        registry_service.set_representative_status(
            patch.mersis, patch.rep_id, patch.status, settings
        )

    # From here on this is an ordinary application: the service below never
    # learns which case, if any, produced it.
    application = application_service.create_application(
        session, case.application, correlation_id=correlation_id
    )

    audit_service.record_branch_action(
        session,
        action=AuditAction.DEMO_CASE_LOADED,
        entity_type=AuditEntity.DEMO,
        entity_id=application.id,
        correlation_id=correlation_id,
        detail={
            "case": case.case,
            "title": case.title,
            "registry_patch": [patch.model_dump(mode="json") for patch in case.registry_patch],
        },
    )

    assert application.id is not None  # assigned by the flush in create_application
    return application.id


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def reset_demo(settings: Settings | None = None, *, correlation_id: str | None = None) -> dict[str, Any]:
    """Restore the demo to its committed baseline in one action (§8.2).

    Restores the database, the runtime registry and demo uploads.

    The **extraction cache is deliberately left alone**. GAP-11 pre-warms cases
    2-4 during final rehearsal and the section 16 runbook has the presenter run
    this reset immediately before the judged run — wiping the cache here would
    silently discard exactly the state the stage policy depends on. Clearing it
    is a separate, explicit operation (`ExtractionCache.clear`).
    """
    settings = settings or get_settings()
    correlation_id = correlation_id or audit_service.new_correlation_id()

    settings.ensure_runtime_directories()

    # 1. Database: drop and recreate for a byte-identical baseline every time.
    drop_all(settings)
    init_db(settings)

    # 2. Runtime registry from the committed seed.
    registry_service.reset_to_seed(settings)

    # 3. Demo uploads.
    removed_uploads = clear_runtime_directory(settings.uploads_path, settings)

    with session_scope() as session:
        audit_service.record_branch_action(
            session,
            action=AuditAction.DEMO_RESET,
            entity_type=AuditEntity.DEMO,
            correlation_id=correlation_id,
            detail={"removed_uploads": removed_uploads},
        )

    # No absolute paths in the response body (section 5.7): the CLI below prints
    # them for the operator, but the HTTP surface does not hand out the layout.
    return {
        "ok": True,
        "removed_uploads": removed_uploads,
        "registry_restored": True,
        "correlation_id": correlation_id,
    }


def clear_runtime_directory(directory: Path, settings: Settings | None = None) -> int:
    """Delete the contents of a configured runtime directory. Returns file count.

    Plan Phase 0 backend step 6: "Confirm reset targets resolve only inside the
    configured runtime data directories", and section 8.2: reset "must not delete
    files outside configured runtime directories". Two guards enforce that — the
    directory must be one this configuration declares writable, and every entry
    is re-resolved under it before deletion, so a symlink planted in `uploads/`
    cannot redirect the delete elsewhere.
    """
    settings = settings or get_settings()
    target = directory.resolve()
    if target not in {path.resolve() for path in settings.writable_directories()}:
        raise ValueError(
            f"Refusing to clear {target}: not a configured runtime directory. "
            f"Allowed: {[str(p) for p in settings.writable_directories()]}"
        )
    if not target.is_dir():
        return 0

    removed = 0
    for entry in sorted(target.iterdir()):
        if entry.name == ".gitkeep":
            continue
        safe = resolve_under(target, entry.name)
        if safe.is_dir() and not safe.is_symlink():
            removed += _remove_tree(safe)
        else:
            safe.unlink()
            removed += 1
    return removed


def _remove_tree(directory: Path) -> int:
    removed = 0
    for entry in sorted(directory.iterdir()):
        if entry.is_dir() and not entry.is_symlink():
            removed += _remove_tree(entry)
        else:
            entry.unlink()
            removed += 1
    directory.rmdir()
    return removed


# ---------------------------------------------------------------------------
# CLI — used by scripts/reset_demo.ps1 and scripts/reset_demo.sh
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover - exercised through the reset scripts
    import sys

    from api.config import load_settings_or_exit

    # The presenter runs this from a Windows console whose default code page
    # cannot represent "tamamlandı". Without this the reset output arrives as
    # mojibake at exactly the moment someone is checking it worked.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    settings = load_settings_or_exit()
    if not settings.demo_mode:
        print("DEMO_MODE is false; refusing to reset. Set DEMO_MODE=true in api/.env.")
        raise SystemExit(3)

    result = reset_demo(settings)
    print("YetkiCheck demo reset tamamlandı.")
    print(f"  database : {settings.database_path}")
    print(f"  registry : {settings.registry_path}")
    print(f"  uploads  : {result['removed_uploads']} dosya silindi")
    print(f"  cache    : {settings.cache_path} (korundu — GAP-11 ön ısıtma)")


if __name__ == "__main__":  # pragma: no cover
    main()
