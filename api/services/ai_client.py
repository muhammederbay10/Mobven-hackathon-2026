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

Status: Phase 0 backend step 7 defines the modes and the cache. The transport
for `/extract` and `/analyze` is task `P1-01`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from api.config import AIMode, CacheMode, Settings, get_settings, resolve_under
from api.errors import ApiError
from api.schemas import (
    SCHEMA_VERSION,
    AnalyzeRequest,
    CheckReport,
    ErrorCode,
    ExtractionResult,
)

__all__ = [
    "AIMode",
    "CacheMode",
    "AIServiceClient",
    "ExtractionCache",
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

    def put(self, extraction: ExtractionResult) -> Path | None:
        """Store a validated extraction. Returns the written path, or None if off."""
        if not self.enabled:
            return None
        path = self.path_for(
            cache_key(extraction.document_sha256, extraction.schema_version, extraction.engine)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(extraction.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
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
    """The two business endpoints, plus infrastructure health (GAP-03).

    ``GET /health`` is infrastructure and does not count as one of the two
    business endpoints. The API loads registry data and passes it into
    ``/analyze``; the AI service never reads ``registry.json``, application rows
    or uploaded files by path.
    """

    async def health(self) -> bool: ...

    async def extract(self, *, file_bytes: bytes, filename: str, document_id: int) -> ExtractionResult: ...

    async def analyze(self, request: AnalyzeRequest) -> CheckReport: ...


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
        "extraction_cache": settings.extraction_cache.value,
        "cache_ready": settings.cache_path.is_dir(),
        "cached_extractions": (
            len(list(settings.cache_path.glob("*.json"))) if settings.cache_path.is_dir() else 0
        ),
        "timeout_seconds": settings.ai_timeout_seconds,
    }
