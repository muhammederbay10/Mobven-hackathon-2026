# ai/scripts/check_render.py
"""Renders one document and reports page count, dimensions, and byte sizes at both resolutions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.render import PageImages, RenderError, extract_dpi, render_path, sort_dpi  # noqa: E402

# data/ holds the documents that go on stage and into screenshots. Rendered previews of a real
# circular carry real people's names, so they may never be written there.
STAGE_ASSETS = REPO_ROOT / "data"


def format_bytes(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"


def format_size(size: tuple[int, int]) -> str:
    return f"{size[0]} x {size[1]}"


def print_pages(pages: list[PageImages]) -> None:
    print(f"  {'page':>4}  {'sort':<14}{'bytes':>10}   {'extract':<14}{'bytes':>10}")
    for page in pages:
        print(
            f"  {page.page_no:>4}  {format_size(page.sort_size):<14}"
            f"{format_bytes(len(page.sort_png)):>10}   "
            f"{format_size(page.extract_size):<14}{format_bytes(len(page.extract_png)):>10}"
        )
    sort_total = sum(len(page.sort_png) for page in pages)
    extract_total = sum(len(page.extract_png) for page in pages)
    print(
        f"  {'total':>4}  {'':<14}{format_bytes(sort_total):>10}   "
        f"{'':<14}{format_bytes(extract_total):>10}"
    )


def write_previews(pages: list[PageImages], destination: Path, stem: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for page in pages:
        (destination / f"{stem}-p{page.page_no}-sort.png").write_bytes(page.sort_png)
        (destination / f"{stem}-p{page.page_no}-extract.png").write_bytes(page.extract_png)
    print(f"previews    {2 * len(pages)} file(s) written to {destination}")
    print("            internal only — never copy a real document's pages into data/ or the deck")


def is_inside(candidate: Path, parent: Path) -> bool:
    return parent == candidate or parent in candidate.parents


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one document at both resolutions.")
    parser.add_argument("path", type=Path, help="PDF, JPG, JPEG, or PNG to render")
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        metavar="DIR",
        help="also write the rendered PNGs into DIR for eyeballing (not under data/)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    path = args.path

    print("YetkiCheck — render stage\n")
    print(f"file        {path}")
    print(f"dpi         sort {sort_dpi()} · extract {extract_dpi()}")

    try:
        pages = render_path(path)
    except RenderError as error:
        print(f"FAILED      {type(error).__name__}: {error}")
        return 1

    print(f"pages       {len(pages)}\n")
    print_pages(pages)
    print()

    if args.preview is None:
        print("previews    not written (use --preview DIR to inspect the images)")
        return 0

    destination = args.preview.resolve()
    if is_inside(destination, STAGE_ASSETS):
        print(f"FAILED      previews may not be written under {STAGE_ASSETS} (stage assets)")
        return 1
    write_previews(pages, destination, path.stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
