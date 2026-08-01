"""Shared pytest fixtures and path helpers for the bank API test suite.

Contract tests must run with no network access at all (Phase 0 shared
architecture step 5). Everything here resolves to committed local files.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Allow `import api.schemas` when pytest is invoked from anywhere.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --- delivery locations -----------------------------------------------------
# AI-engineer-owned deliverables (IMPLEMENTATION_PLAN.md GAP-10, due H4).
# This track reads them; it never creates or edits them.
AI_FIXTURES_DIR = REPO_ROOT / "ai" / "tests" / "fixtures"

# Full-stack-owned demo data.
DATA_DIR = REPO_ROOT / "data"
EXTRACTION_FIXTURES_DIR = DATA_DIR / "fixtures" / "extractions"
REPORT_FIXTURES_DIR = DATA_DIR / "fixtures" / "reports"
CASES_FILE = DATA_DIR / "fixtures" / "cases.json"
REGISTRY_SEED_FILE = DATA_DIR / "registry.seed.json"

CASE_NUMBERS = (1, 2, 3, 4)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_json(*directories: Path) -> list[tuple[str, object]]:
    """Return (label, payload) for every committed JSON file in `directories`."""
    found: list[tuple[str, object]] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            found.append((str(path.relative_to(REPO_ROOT)).replace("\\", "/"), load_json(path)))
    return found


def require_delivered(payloads: list[tuple[str, object]], what: str) -> None:
    """Skip with an explicit hand-off message when a deliverable is still pending.

    A skip here means "the AI engineer has not delivered yet", never "this
    assertion is optional". After the H4 freeze these skips must disappear.
    """
    if not payloads:
        pytest.skip(
            f"{what} not delivered yet — expected under {AI_FIXTURES_DIR.relative_to(REPO_ROOT)} "
            f"or {EXTRACTION_FIXTURES_DIR.relative_to(REPO_ROOT)} (GAP-10, due H4)."
        )


# ---------------------------------------------------------------------------
# Isolated runtime environment
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A throwaway data directory and database, seeded from committed fixtures.

    Tests must never touch the developer's real `data/registry.json`, uploads or
    database — a test run that mutates the demo baseline is exactly the kind of
    surprise that ruins a rehearsal. Committed inputs are copied in read-only
    spirit; everything mutable lives under `tmp_path`.
    """
    from api import config, db

    data_dir = tmp_path / "data"
    (data_dir / "fixtures").mkdir(parents=True)
    (data_dir / "uploads").mkdir(parents=True)
    (data_dir / "cache" / "extractions").mkdir(parents=True)
    (data_dir / "documents").mkdir(parents=True)

    shutil.copy(REGISTRY_SEED_FILE, data_dir / "registry.seed.json")
    shutil.copy(CASES_FILE, data_dir / "fixtures" / "cases.json")
    for fixture_dir in (EXTRACTION_FIXTURES_DIR, REPORT_FIXTURES_DIR):
        if fixture_dir.is_dir():
            shutil.copytree(fixture_dir, data_dir / "fixtures" / fixture_dir.name)
    for document in (DATA_DIR / "documents").glob("case[1-3].pdf"):
        shutil.copy(document, data_dir / "documents" / document.name)

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_MODE", "stub")
    monkeypatch.setenv("EXTRACTION_CACHE", "on")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")

    config.get_settings.cache_clear()
    db.reset_engine()

    settings = config.get_settings()
    settings.ensure_runtime_directories()
    db.init_db(settings)

    yield settings

    db.reset_engine()
    config.get_settings.cache_clear()


@pytest.fixture
def client(demo_env):
    """TestClient bound to the isolated environment. No network involved."""
    from fastapi.testclient import TestClient

    from api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
