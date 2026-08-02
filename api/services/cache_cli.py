"""Operator CLI for clearing backend-owned reusable AI results.

This intentionally does not reset SQLite, the runtime registry, uploads, or
source documents. ``scripts/clear_caches.ps1`` is the Windows entry point.
"""

from __future__ import annotations

from api.config import get_settings
from api.services.ai_client import ExtractionCache


def main() -> int:
    settings = get_settings()
    settings.ensure_runtime_directories()
    cache = ExtractionCache(settings)
    removed = cache.clear()
    print(f"AI extraction cache cleared: {removed} file(s) removed.")
    print(f"Cache directory: {cache.directory}")
    print("Database, registry, uploads and source documents were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
