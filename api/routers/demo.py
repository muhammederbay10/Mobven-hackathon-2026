"""Demo control endpoints — plan section 8.2.

Every route here is guarded by ``DEMO_MODE`` (section 14: "Demo mutation
endpoints require DEMO_MODE=true"). Routers stay thin: they validate, delegate
to ``demo_service`` and serialize. No business rule lives in this file.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlmodel import Session

from api.config import Settings, get_settings
from api.db import get_session
from api.errors import demo_mode_disabled
from api.services import demo_service
from api.services.ai_client import ExtractionCache

router = APIRouter(prefix="/api/demo", tags=["demo"])


def require_demo_mode(settings: Annotated[Settings, Depends(get_settings)]) -> Settings:
    """Reject every demo-only mutation when DEMO_MODE is false."""
    if not settings.demo_mode:
        raise demo_mode_disabled()
    return settings


@router.get("/cases")
def list_cases(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Case cards for the control panel (plan section 10.2).

    Read-only, so it is not behind the DEMO_MODE mutation guard. Serving the
    fixture keeps the Turkish copy and the expected-outcome labels in one place —
    the frontend renders them, and no frontend code branches on a case number.
    """
    cases = demo_service.load_cases(settings)
    return {
        "cases": [
            {
                "case": case.case,
                "title": case.title,
                "description": case.description,
                "expected_verdict": case.expected_verdict.value,
            }
            for case in cases.cases
        ]
    }


@router.post("/load-case/{case_number}", status_code=status.HTTP_201_CREATED)
def load_case(
    case_number: int,
    request: Request,
    settings: Annotated[Settings, Depends(require_demo_mode)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, int]:
    """Create a persistent application from a demo case fixture."""
    correlation_id = request.state.correlation_id
    application_id = demo_service.load_case(
        session, case_number, correlation_id=correlation_id, settings=settings
    )
    session.commit()
    return {"application_id": application_id}


@router.post("/reset")
def reset(
    request: Request,
    settings: Annotated[Settings, Depends(require_demo_mode)],
) -> dict[str, Any]:
    """Restore database rows, runtime registry and demo uploads to baseline."""
    return demo_service.reset_demo(settings, correlation_id=request.state.correlation_id)


@router.post("/cache/prewarm")
async def prewarm_cache(
    settings: Annotated[Settings, Depends(require_demo_mode)],
) -> dict[str, Any]:
    return await demo_service.prewarm_extraction_cache(settings)


@router.post("/cache/clear")
def clear_cache(
    settings: Annotated[Settings, Depends(require_demo_mode)],
    document_sha256: str | None = None,
) -> dict[str, int]:
    return {"removed": ExtractionCache(settings).clear(document_sha256)}
