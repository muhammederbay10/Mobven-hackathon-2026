"""Validated configuration for the YetkiCheck bank API.

Plan section 4.3: an unknown ``AI_MODE`` (or ``EXTRACTION_CACHE``) value "must
fail application startup with a clear configuration error" — a misconfigured
demo should refuse to boot at the venue rather than behave surprisingly on stage.

Path resolution
---------------
``DATA_DIR`` and a relative SQLite path are resolved against the **repository
root**, not the current working directory. The plan ships ``DATA_DIR=../data``
in ``api/.env.example`` (relative to ``api/``) while section 4.4 starts the app
from the repository root with ``python -m uvicorn api.main:app``. Anchoring to
the package location makes both true at once and keeps the repo portable
regardless of where a command is invoked from.
"""

from __future__ import annotations

import sys
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parent


class ConfigurationError(RuntimeError):
    """Raised when configuration is invalid. Always fatal at startup."""


class AIMode(str, Enum):
    """Plan section 4.3."""

    STUB = "stub"  # committed golden fixtures, optional short artificial delay
    LIVE = "live"  # call the AI service at AI_URL
    REPLAY = "replay"  # cached validated live response, selected by document SHA-256


class CacheMode(str, Enum):
    ON = "on"
    OFF = "off"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(API_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"

    # Guards every demo-only mutation endpoint (plan section 14).
    demo_mode: bool = True

    database_url: str = "sqlite:///./yetkicheck.db"

    # The externally owned AI service. This track configures the URL and verifies
    # connectivity; it never starts, stops or edits that service.
    ai_url: str = "http://localhost:8001"
    ai_mode: AIMode = AIMode.STUB
    extraction_cache: CacheMode = CacheMode.ON
    ai_timeout_seconds: float = 20.0

    data_dir: str = "../data"
    allowed_origins: str = "http://localhost:3000"
    max_upload_mb: int = 20

    # --- validation --------------------------------------------------------

    @field_validator("ai_mode", mode="before")
    @classmethod
    def _validate_ai_mode(cls, value: object) -> object:
        return _one_of(value, AIMode, "AI_MODE")

    @field_validator("extraction_cache", mode="before")
    @classmethod
    def _validate_extraction_cache(cls, value: object) -> object:
        return _one_of(value, CacheMode, "EXTRACTION_CACHE")

    @field_validator("ai_timeout_seconds")
    @classmethod
    def _positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("AI_TIMEOUT_SECONDS must be greater than zero.")
        return value

    @field_validator("max_upload_mb")
    @classmethod
    def _positive_upload_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_UPLOAD_MB must be greater than zero.")
        return value

    # --- derived values ----------------------------------------------------

    @property
    def cache_enabled(self) -> bool:
        return self.extraction_cache is CacheMode.ON

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        """Plan section 14: CORS allows only configured frontend origins."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    # --- runtime directories ----------------------------------------------

    @property
    def data_path(self) -> Path:
        candidate = Path(self.data_dir)
        if not candidate.is_absolute():
            candidate = API_DIR / candidate
        return candidate.resolve()

    @property
    def uploads_path(self) -> Path:
        return self.data_path / "uploads"

    @property
    def cache_path(self) -> Path:
        """Backend-owned extraction cache. The AI service never writes here."""
        return self.data_path / "cache" / "extractions"

    @property
    def documents_path(self) -> Path:
        return self.data_path / "documents"

    @property
    def fixtures_path(self) -> Path:
        return self.data_path / "fixtures"

    @property
    def registry_path(self) -> Path:
        """Runtime registry. Generated from the seed at reset; git-ignored."""
        return self.data_path / "registry.json"

    @property
    def registry_seed_path(self) -> Path:
        return self.data_path / "registry.seed.json"

    @property
    def cases_path(self) -> Path:
        return self.fixtures_path / "cases.json"

    @property
    def database_path(self) -> Path | None:
        """Filesystem path of the SQLite database, or None for other engines."""
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        raw = self.database_url[len(prefix) :]
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate.resolve()

    @property
    def sqlalchemy_url(self) -> str:
        """`database_url` with any relative SQLite path anchored to the repo root."""
        path = self.database_path
        return f"sqlite:///{path}" if path is not None else self.database_url

    # --- runtime directories that must exist -------------------------------

    def writable_directories(self) -> tuple[Path, ...]:
        """Every directory the API is allowed to create or delete files in.

        Plan Phase 0 backend step 6 and section 14: reset targets and upload
        paths must resolve *only* inside these. `resolve_under` is the guard.
        """
        return (self.uploads_path, self.cache_path)

    def ensure_runtime_directories(self) -> None:
        for directory in (*self.writable_directories(), self.data_path):
            directory.mkdir(parents=True, exist_ok=True)


def _one_of(value: object, enum_cls: type[Enum], env_name: str) -> object:
    """Turn an unknown enum value into a message a tired presenter can act on."""
    if isinstance(value, enum_cls):
        return value
    allowed = [member.value for member in enum_cls]
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    raise ValueError(f"{env_name}={value!r} is not valid. Allowed values: {', '.join(allowed)}.")


def resolve_under(base: Path, *parts: str | Path) -> Path:
    """Resolve `parts` under `base`, refusing anything that escapes it.

    Plan section 14: "Verify every resolved upload/page path remains under the
    configured data directory." Covers `..` traversal, absolute-path injection
    and symlinks, because both sides are fully resolved before comparison.
    """
    base_resolved = base.resolve()
    candidate = base_resolved.joinpath(*[Path(part) for part in parts]).resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise ConfigurationError(f"Path {candidate} escapes its base directory {base_resolved}.")
    return candidate


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and validate settings once per process.

    Raises ConfigurationError — never a bare pydantic ValidationError — so the
    startup failure reads as a configuration problem rather than a stack trace.
    """
    try:
        return Settings()
    except ValidationError as exc:
        problems = "\n".join(
            f"  - {'.'.join(str(p) for p in err['loc']).upper()}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigurationError(
            "YetkiCheck API configuration is invalid. Fix api/.env and restart:\n" + problems
        ) from exc


def load_settings_or_exit() -> Settings:
    """Entry-point helper: print the configuration problem and exit non-zero."""
    try:
        return get_settings()
    except ConfigurationError as exc:  # pragma: no cover - exercised by the CLI
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
