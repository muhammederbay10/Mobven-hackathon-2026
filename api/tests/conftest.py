"""Shared pytest fixtures and path helpers for the bank API test suite.

Contract tests must run with no network access at all (Phase 0 shared
architecture step 5). Everything here resolves to committed local files.
"""

from __future__ import annotations

import json
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
