"""FastAPI application factory — plan sections 4.3, 5.7, 8.1, 14 and 15.

Startup fails loudly on invalid configuration (section 4.3), CORS admits only
the configured frontend origins (section 14), every request carries a
correlation ID (section 15), and every non-2xx response uses the standard error
envelope with no stack trace, raw model response, local path or secret in it
(sections 5.7 and 14).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.config import AIMode, ConfigurationError, Settings, get_settings
from api.db import get_engine, init_db
from api.errors import ApiError
from api.routers import demo
from api.schemas import ErrorCode
from api.services import ai_client, registry_service
from api.services.audit_service import new_correlation_id, redact

logger = logging.getLogger("yetkicheck.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_runtime_directories()
    init_db(settings)
    logger.info(
        "yetkicheck api ready",
        extra={"ai_mode": settings.ai_mode.value, "demo_mode": settings.demo_mode},
    )
    yield


def create_app() -> FastAPI:
    """Build the application. Raises ConfigurationError before serving anything."""
    settings = get_settings()  # ConfigurationError here is fatal, by design

    app = FastAPI(
        title="YetkiCheck Bank API",
        version="0.1.0",
        summary="İmza sirküleri doğrulama ve yetki denetimi",
        lifespan=lifespan,
    )

    # Section 14: CORS allows only configured frontend origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT"],
        allow_headers=["Content-Type"],
    )

    _register_middleware(app)
    _register_error_handlers(app)
    _register_infrastructure_routes(app)
    app.include_router(demo.router)
    return app


# ---------------------------------------------------------------------------
# Middleware — plan section 15
# ---------------------------------------------------------------------------


def _register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlate_and_log(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        """One correlation ID per request, threaded through errors and audit rows.

        The structured log carries route, status and duration but never a
        payload: section 14 forbids logging document bytes, extracted personal
        data, authorization headers or environment variables.
        """
        correlation_id = request.headers.get("x-correlation-id") or new_correlation_id()
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "request failed",
                extra={
                    "correlation_id": correlation_id,
                    "route": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Correlation-Id"] = correlation_id
        logger.info(
            "request",
            extra={
                "correlation_id": correlation_id,
                "route": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


# ---------------------------------------------------------------------------
# Error handling — plan section 5.7
# ---------------------------------------------------------------------------


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=exc.to_body(_correlation_id(request))
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Field-level detail so the branch UI can render errors per field (§10.3).

        The pydantic `input` value is dropped rather than echoed: it can contain
        the very identifiers section 14 keeps out of responses and logs.
        """
        details = {
            "fields": [
                {
                    "path": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"]),
                    "message": error["msg"],
                }
                for error in exc.errors()
            ]
        }
        error = ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Gönderilen bilgiler geçersiz.",
            status_code=422,
            details=redact(details),
        )
        return JSONResponse(status_code=422, content=error.to_body(_correlation_id(request)))

    @app.exception_handler(registry_service.RegistryUnavailableError)
    async def handle_registry_unavailable(
        request: Request, exc: registry_service.RegistryUnavailableError
    ) -> JSONResponse:
        """Section 15: a registry read failure fails closed."""
        from api.errors import registry_unavailable

        logger.error(
            "registry unavailable",
            extra={"correlation_id": _correlation_id(request), "detail": str(exc)},
        )
        error = registry_unavailable()
        return JSONResponse(
            status_code=error.status_code, content=error.to_body(_correlation_id(request))
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """Last resort. The original exception is logged, never returned."""
        correlation_id = _correlation_id(request)
        logger.exception("unhandled error", extra={"correlation_id": correlation_id})
        error = ApiError(
            ErrorCode.INTERNAL_ERROR,
            "Beklenmeyen bir hata oluştu.",
            status_code=500,
            retryable=True,
        )
        return JSONResponse(status_code=500, content=error.to_body(correlation_id))


# ---------------------------------------------------------------------------
# Infrastructure routes — plan section 8.1
# ---------------------------------------------------------------------------


def _register_infrastructure_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["infrastructure"])
    def health() -> dict[str, Any]:
        """Process and database health. Deliberately does not require the AI service.

        Section 8.1: an AI outage must not make the bank API look unhealthy —
        stub and replay modes are expected to work with the AI service stopped.
        """
        database_ok = _database_ok()
        return {"status": "ok" if database_ok else "degraded", "database": database_ok}

    @app.get("/ready", tags=["infrastructure"])
    async def ready(
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> JSONResponse:
        """Database, data directory and configured AI-mode readiness (§8.1).

        AI reachability is *reported*, never owned: this track configures
        `AI_URL` and checks it, while the AI engineer starts and stops the
        process (Phase 0 done-when, section 18.11). In stub and replay modes
        reachability is not applicable and never blocks readiness.
        """
        checks: dict[str, Any] = {
            "database": _database_ok(),
            "data_dir": settings.data_path.is_dir(),
            "registry_seed": settings.registry_seed_path.is_file(),
            "cases_fixture": settings.cases_path.is_file(),
            "uploads_dir": settings.uploads_path.is_dir(),
            "cache_dir": settings.cache_path.is_dir(),
            "ai": ai_client.describe_mode(settings),
        }
        checks["ai"]["reachable"] = await _ai_reachable(settings)

        blocking = [
            key
            for key in ("database", "data_dir", "registry_seed", "cases_fixture")
            if not checks[key]
        ]
        if settings.ai_mode is AIMode.LIVE and checks["ai"]["reachable"] is False:
            blocking.append("ai")

        ready_now = not blocking
        return JSONResponse(
            status_code=200 if ready_now else 503,
            content={"ready": ready_now, "blocking": blocking, "checks": checks},
        )


def _database_ok() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # pragma: no cover - only on a genuinely broken database
        logger.exception("database health check failed")
        return False


async def _ai_reachable(settings: Settings) -> bool | None:
    """None when reachability does not apply to the configured mode."""
    if settings.ai_mode is not AIMode.LIVE:
        return None
    try:
        async with httpx.AsyncClient(timeout=min(settings.ai_timeout_seconds, 3.0)) as client:
            response = await client.get(f"{settings.ai_url.rstrip('/')}/health")
        return response.status_code == 200
    except Exception:
        return False


try:
    app = create_app()
except ConfigurationError as exc:  # pragma: no cover - fatal by design
    raise SystemExit(f"\n{exc}\n") from exc
