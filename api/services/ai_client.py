"""Typed client for the externally owned AI service — plan sections 4.3 and 8.6.

Ownership boundary (section 18.11): the AI engineer owns `ai/` — the extractor,
the prompts, the nine-check comparison engine and the service process. This
module is the *only* place the bank API touches it. Full-stack work here is
limited to transport, mode selection, timeout translation and the cache.

What this module owns, and the AI service explicitly does not
------------------------------------------------------------
The **extraction cache**. Section 4.3: "The bank API owns the extraction cache
under ``data/cache/extractions/``. The AI service remains stateless and
file-system-free." That split is what lets the AI engineer restart their service
mid-rehearsal without disturbing pre-warmed stage data (P1-01 acceptance).

Cache key format (frozen here, backend-owned)
---------------------------------------------
``(document_sha256, schema_version, engine)`` — section 8.8. Rendered as::

    <sha256>__<schema_version>__<engine-slug>.json

The document hash is what makes case 4 reuse case 1's clean document for free;
``schema_version`` and ``engine`` are in the key so a contract bump or a model
change can never serve a stale payload shaped for the previous one.

Status: `/analyze` transport and the flat-contract adapter are implemented.
`/extract` remains guarded by `AI_EXTRACT_AVAILABLE` until external delivery.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import ValidationError

from api.config import AIMode, CacheMode, Settings, get_settings, resolve_under
from api.errors import ApiError
from api.schemas import (
    SCHEMA_VERSION,
    AIHealthResponse,
    AnalyzeRegistryCompany,
    AnalyzeRegistryRepresentative,
    AnalyzeRequest,
    ApplicationContext,
    CheckReport,
    ErrorCode,
    ExtractionResult,
    Registry,
)

__all__ = [
    "AIMode",
    "CacheMode",
    "AIServiceClient",
    "LiveAIServiceClient",
    "ExtractionCache",
    "build_analyze_request",
    "cache_key",
    "ai_contract_error",
    "ai_timeout_error",
    "ai_unavailable_error",
]

_ENGINE_SLUG = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Cache key and store
# ---------------------------------------------------------------------------


def _slug(value: str) -> str:
    """Filesystem-safe, lossless-enough rendering of an engine identifier."""
    return _ENGINE_SLUG.sub("-", value.strip().lower()).strip("-") or "unknown"


def cache_key(document_sha256: str, schema_version: str, engine: str) -> str:
    """The backend-owned cache key (section 8.8)."""
    return f"{document_sha256.lower()}__{_slug(schema_version)}__{_slug(engine)}"


class ExtractionCache:
    """File-backed cache of *validated* `/extract` responses.

    Only payloads that already satisfy the frozen contract are stored, so a
    cache hit can never reintroduce a malformed response that live mode would
    have rejected. Every path is resolved with `resolve_under`, so a crafted
    hash or engine string cannot write outside the cache directory (section 14).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self._settings.cache_enabled

    @property
    def directory(self) -> Path:
        return self._settings.cache_path

    def path_for(self, key: str) -> Path:
        return resolve_under(self.directory, f"{key}.json")

    def get(self, document_sha256: str, engine: str) -> ExtractionResult | None:
        """Return a cached extraction, or None on a miss or an unusable entry.

        A corrupt or contract-violating cache entry is treated as a miss rather
        than an error: the correct response is to call the model again, not to
        fail the demo over a bad file on disk.
        """
        if not self.enabled:
            return None
        path = self.path_for(cache_key(document_sha256, SCHEMA_VERSION, engine))
        if not path.is_file():
            return None
        try:
            return ExtractionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError):
            return None

    def put(
        self,
        extraction: ExtractionResult,
        *,
        document_sha256: str,
        engine: str,
    ) -> Path | None:
        """Store a validated extraction. Returns the written path, or None if off."""
        if not self.enabled:
            return None
        path = self.path_for(
            cache_key(document_sha256, extraction.schema_version, engine)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                extraction.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def clear(self, document_sha256: str | None = None) -> int:
        """Clear the cache, or just one document's entries. Returns files removed.

        GAP-11 stage policy: cases 2-4 stay pre-warmed while case 1's entry is
        cleared before the judged run, so its first extraction genuinely calls
        the model.
        """
        if not self.directory.is_dir():
            return 0
        prefix = None if document_sha256 is None else f"{document_sha256.lower()}__"
        removed = 0
        for path in self.directory.glob("*.json"):
            if prefix is not None and not path.name.startswith(prefix):
                continue
            path.unlink()
            removed += 1
        return removed


# ---------------------------------------------------------------------------
# Error translation 
# ---------------------------------------------------------------------------


def ai_timeout_error(seconds: float) -> ApiError:
    return ApiError(
        ErrorCode.AI_TIMEOUT,
        "Belge analizi zaman aşımına uğradı. Tekrar deneyebilirsiniz.",
        status_code=504,
        retryable=True,
        details={"timeout_seconds": seconds},
    )


def ai_unavailable_error() -> ApiError:
    return ApiError(
        ErrorCode.AI_UNAVAILABLE,
        "Analiz servisine ulaşılamadı. Tekrar deneyebilirsiniz.",
        status_code=503,
        retryable=True,
    )


def ai_contract_error(detail: str) -> ApiError:
    """An AI response that does not match the frozen contract.

    Section 15: store no partial extraction or report and return a retryable
    integration error. Section 8.8: record the defect and hand it to the AI
    engineer — never patch `ai/`, and never special-case the verdict here.
    The raw payload is deliberately *not* echoed to the client (section 5.7).
    """
    return ApiError(
        ErrorCode.AI_CONTRACT_ERROR,
        "Analiz servisinden beklenen biçimde yanıt alınamadı.",
        status_code=502,
        retryable=True,
        details={"contract": detail},
    )


# ---------------------------------------------------------------------------
# Client interface
# ---------------------------------------------------------------------------


class AIServiceClient(Protocol):
    """AI service boundary plus infrastructure health.

    ``POST /analyze`` is delivered. ``POST /extract`` remains in the interface
    because the bank orchestration will need it, but current readiness reports
    it as unavailable until the AI engineer delivers it.
    """

    async def health(self) -> bool: ...

    async def extract(self, *, file_bytes: bytes, filename: str, document_id: int) -> ExtractionResult: ...

    async def analyze(self, request: AnalyzeRequest) -> CheckReport: ...


class LiveAIServiceClient:
    """Strict HTTP consumer for the externally owned AI process."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.ai_url.rstrip("/"),
                timeout=self._settings.ai_timeout_seconds,
                transport=self._transport,
            ) as client:
                return await client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ai_timeout_error(self._settings.ai_timeout_seconds) from exc
        except httpx.RequestError as exc:
            raise ai_unavailable_error() from exc

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/health")
            if response.status_code != 200:
                return False
            AIHealthResponse.model_validate(response.json())
            return True
        except (ApiError, ValueError, ValidationError):
            return False

    async def extract(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        document_id: int,
    ) -> ExtractionResult:
        if not self._settings.ai_extract_available:
            raise ai_unavailable_error()
        response = await self._request(
            "POST",
            "/extract",
            files={"file": (filename, file_bytes, "application/octet-stream")},
            data={"document_id": str(document_id)},
        )
        return _validated_response(response, ExtractionResult)

    async def analyze(self, request: AnalyzeRequest) -> CheckReport:
        response = await self._request(
            "POST",
            "/analyze",
            json=request.model_dump(mode="json", by_alias=True),
        )
        return _validated_response(response, CheckReport)


def _validated_response(response: httpx.Response, model: type[ExtractionResult] | type[CheckReport]):
    if response.status_code >= 500:
        raise ai_unavailable_error()
    if response.status_code != 200:
        raise ai_contract_error(f"unexpected HTTP status {response.status_code}")
    try:
        return model.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise ai_contract_error("response failed schema validation") from exc


def build_analyze_request(
    *,
    extraction: ExtractionResult,
    company_name: str,
    tax_number: str,
    mersis: str,
    applicant_name: str,
    applicant_tckn_masked: str,
    branch_code: str,
    identity_verified_at_branch: bool,
    registry: Registry,
    as_of: str | None = None,
) -> AnalyzeRequest:
    """Project bank-owned records into the AI service's older flat request.

    This adapter is intentionally at the transport boundary. The bank registry
    stays in its stable-ID envelope while ``/analyze`` receives the keyed
    ``{mersis: {name,status,reps}}`` shape documented by the AI engineer.
    """

    companies = {
        company.mersis: AnalyzeRegistryCompany(
            name=company.legal_name,
            status=company.status.value,
            reps=[
                AnalyzeRegistryRepresentative(
                    name=representative.name,
                    tckn=representative.tckn,
                    mode=representative.mode.value,
                    status=representative.status.value,
                )
                for representative in company.representatives
            ],
        )
        for company in registry.companies
    }
    return AnalyzeRequest(
        extraction=extraction,
        application=ApplicationContext(
            company_name=company_name,
            tax_number=tax_number,
            mersis=mersis,
            applicant_name=applicant_name,
            applicant_tckn=applicant_tckn_masked,
            branch_code=branch_code,
            identity_verified_at_branch=identity_verified_at_branch,
        ),
        registry=companies,
        as_of=as_of,
    )


def describe_mode(settings: Settings | None = None) -> dict[str, object]:
    """Readiness/diagnostic summary of how this process talks to the AI service.

    Reports whether the cache directory is usable rather than where it lives:
    section 5.7 keeps local paths out of API responses, and a readiness probe is
    no more entitled to leak the filesystem layout than an error body is.
    """
    settings = settings or get_settings()
    return {
        "ai_mode": settings.ai_mode.value,
        "ai_url": settings.ai_url if settings.ai_mode is AIMode.LIVE else None,
        "extract_available": settings.ai_extract_available,
        "extraction_cache": settings.extraction_cache.value,
        "cache_ready": settings.cache_path.is_dir(),
        "cached_extractions": (
            len(list(settings.cache_path.glob("*.json"))) if settings.cache_path.is_dir() else 0
        ),
        "timeout_seconds": settings.ai_timeout_seconds,
    }
