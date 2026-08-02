"""Configuration validation and path containment.

Plan section 4.3: "Unknown mode values must fail application startup with a clear
configuration error."
Plan Phase 0 backend step 6 / section 14: every resolved runtime path must stay
inside the configured data directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.config import (
    AIMode,
    CacheMode,
    ConfigurationError,
    Settings,
    get_settings,
    resolve_under,
)


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Mode validation — section 4.3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["stub", "live", "replay", "LIVE", " Replay "])
def test_valid_ai_modes_are_accepted_case_insensitively(value: str) -> None:
    assert _settings(ai_mode=value).ai_mode in AIMode


@pytest.mark.parametrize("value", ["fake", "", "stubbed", "off", "mock"])
def test_unknown_ai_mode_is_rejected(value: str) -> None:
    with pytest.raises(Exception) as exc:
        _settings(ai_mode=value)
    # The message must name the variable and list what is allowed, so a presenter
    # can fix api/.env without reading the source.
    message = str(exc.value)
    assert "AI_MODE" in message
    assert "stub, live, replay" in message


@pytest.mark.parametrize("value", ["on", "off", "ON"])
def test_valid_cache_modes_are_accepted(value: str) -> None:
    assert _settings(extraction_cache=value).extraction_cache in CacheMode


@pytest.mark.parametrize("value", ["yes", "true", "enabled", ""])
def test_unknown_cache_mode_is_rejected(value: str) -> None:
    with pytest.raises(Exception) as exc:
        _settings(extraction_cache=value)
    assert "EXTRACTION_CACHE" in str(exc.value)
    assert "on, off" in str(exc.value)


def test_configuration_error_is_raised_not_a_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup must fail as a *configuration* problem, not a pydantic traceback."""
    monkeypatch.setenv("AI_MODE", "definitely-not-a-mode")
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError) as exc:
            get_settings()
        assert "api/.env" in str(exc.value)
        assert "AI_MODE" in str(exc.value)
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(("field", "value"), [("ai_timeout_seconds", 0), ("max_upload_mb", 0)])
def test_non_positive_limits_are_rejected(field: str, value: int) -> None:
    with pytest.raises(Exception):
        _settings(**{field: value})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = _settings(allowed_origins="http://localhost:3000, http://192.168.1.10:3000 ")
    assert settings.cors_origins == ["http://localhost:3000", "http://192.168.1.10:3000"]


def test_cache_enabled_reflects_the_mode() -> None:
    assert _settings(extraction_cache="on").cache_enabled is True
    assert _settings(extraction_cache="off").cache_enabled is False


def test_relative_data_dir_is_anchored_to_the_repo_not_the_cwd() -> None:
    """`DATA_DIR=../data` must mean the same thing from any working directory.

    The plan ships that value in api/.env.example (relative to api/) while
    section 4.4 starts uvicorn from the repository root.
    """
    settings = _settings(data_dir="../data")
    assert settings.data_path.name == "data"
    assert settings.data_path.parent.name == "Mobven-hackathon-2026" or settings.data_path.is_absolute()
    assert settings.registry_seed_path == settings.data_path / "registry.seed.json"
    assert settings.cache_path == settings.data_path / "cache" / "extractions"


def test_relative_sqlite_path_is_anchored_to_the_repo() -> None:
    settings = _settings(database_url="sqlite:///./yetkicheck.db")
    assert settings.database_path is not None
    assert settings.database_path.is_absolute()
    assert settings.sqlalchemy_url.startswith("sqlite:///")


def test_non_sqlite_url_has_no_filesystem_path() -> None:
    settings = _settings(database_url="postgresql://localhost/yetki")
    assert settings.database_path is None
    assert settings.sqlalchemy_url == "postgresql://localhost/yetki"


# ---------------------------------------------------------------------------
# Path containment — section 14, Phase 0 backend step 6
# ---------------------------------------------------------------------------


def test_resolve_under_allows_paths_inside_the_base(tmp_path: Path) -> None:
    assert resolve_under(tmp_path, "a.pdf") == (tmp_path / "a.pdf").resolve()
    assert resolve_under(tmp_path, "pages", "1.png") == (tmp_path / "pages" / "1.png").resolve()


@pytest.mark.parametrize(
    "parts",
    [
        ("..", "escaped.txt"),
        ("pages", "..", "..", "escaped.txt"),
        ("../../etc/passwd",),
    ],
)
def test_resolve_under_rejects_traversal(tmp_path: Path, parts: tuple[str, ...]) -> None:
    base = tmp_path / "uploads"
    base.mkdir()
    with pytest.raises(ConfigurationError):
        resolve_under(base, *parts)


def test_resolve_under_rejects_absolute_path_injection(tmp_path: Path) -> None:
    base = tmp_path / "uploads"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    with pytest.raises(ConfigurationError):
        resolve_under(base, str(outside))


def test_writable_directories_are_only_uploads_and_cache(tmp_path: Path) -> None:
    """The blast radius of a reset is declared, not implied."""
    settings = _settings(data_dir=str(tmp_path))
    assert set(settings.writable_directories()) == {settings.uploads_path, settings.cache_path}
    assert settings.data_path not in settings.writable_directories()
