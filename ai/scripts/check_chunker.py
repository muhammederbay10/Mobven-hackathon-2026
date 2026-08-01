# ai/scripts/check_chunker.py
"""Builds chunks from a PageMap fixture and prints their deterministic routing metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.chunker import Chunk, ChunkerError, build_chunks  # noqa: E402
from ai.render import PageImages  # noqa: E402
from ai.schema import PageMap  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build extraction chunks from a PageMap JSON fixture."
    )
    parser.add_argument("page_map", type=Path, help="JSON fixture validating as ai.schema.PageMap")
    return parser.parse_args(argv)


def fixture_pages(page_map: PageMap) -> list[PageImages]:
    """Creates inert image placeholders; this diagnostic verifies routing, not rendering."""

    return [
        PageImages(
            page_no=page.page,
            sort_png=b"",
            extract_png=f"fixture-page-{page.page}".encode(),
            sort_size=(0, 0),
            extract_size=(0, 0),
        )
        for page in page_map.pages
    ]


def print_chunks(chunks: list[Chunk]) -> None:
    print(f"chunks      {len(chunks)}\n")
    print(f"  {'chunk id':<24}{'agent':<14}{'pages':<14}routing")
    for chunk in chunks:
        pages = ",".join(str(page) for page in chunk.pages)
        routing = "supporting" if chunk.supporting_only else "primary"
        print(f"  {chunk.chunk_id:<24}{chunk.agent:<14}{pages:<14}{routing}")
        print(f"    {chunk.context_header}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    print("YetkiCheck — section-aware chunker\n")
    print(f"page map    {args.page_map}")

    try:
        page_map = PageMap.model_validate_json(args.page_map.read_text(encoding="utf-8"))
        chunks = build_chunks(page_map, fixture_pages(page_map))
    except (OSError, ValidationError, ChunkerError) as error:
        print(f"FAILED      {type(error).__name__}: {error}")
        return 1

    print_chunks(chunks)
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
