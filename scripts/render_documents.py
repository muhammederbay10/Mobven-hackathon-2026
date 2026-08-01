"""Render the synthetic notarial texts to PDFs and page PNGs.

Plan GAP-10 / Phase 0 data steps 3 and 4:

| Deliverable                                   | Owner              | Deadline |
|-----------------------------------------------|--------------------|----------|
| Notarial Turkish text for the four documents  | **AI engineer**    | H2       |
| PDFs and page PNGs under `data/documents/`    | full-stack engineer| H4       |

This script is the H4 half. It reads the AI engineer's committed text and turns
it into the demo documents — it never authors that text, which is an AI-owned
deliverable and a hard dependency of this step.

Drop location for the delivered text (one file per case)::

    data/documents/source/case1.txt … case4.txt

Output::

    data/documents/case1.pdf
    data/documents/pages/case1/page-1.png …

Usage::

    python scripts/render_documents.py                 # render everything present
    python scripts/render_documents.py --case 1        # just one
    python scripts/render_documents.py --font C:/Windows/Fonts/arial.ttf

Turkish text is the whole point of the exercise, so the renderer refuses to run
with a font that cannot draw ``ğ ş İ ı Ç Ö Ü`` rather than emitting the tofu
boxes that would show up on the projector.
"""

from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "data" / "documents" / "source"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "documents"

# A4 at 72 dpi, with a generous margin so the paper reads well when projected.
PAGE_SIZE = fitz.paper_rect("a4")
MARGIN = 56
# 150 dpi keeps page PNGs sharp on a projector without bloating the repo.
PNG_ZOOM = 150 / 72

TURKISH_PROBE = "ğşİıÇÖÜçöü"

FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/calibri.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)


class RenderError(RuntimeError):
    pass


def find_font(explicit: Path | None) -> Path:
    """Locate a font that can actually draw Turkish, or explain what to install."""
    candidates = [explicit] if explicit else list(FONT_CANDIDATES)
    for candidate in candidates:
        if candidate and candidate.is_file() and _supports_turkish(candidate):
            return candidate
    tried = "\n".join(f"  - {c}" for c in candidates if c)
    raise RenderError(
        "No font with full Turkish coverage was found. Tried:\n"
        f"{tried}\n"
        "Pass one explicitly with --font /path/to/font.ttf (Arial, Calibri, "
        "DejaVu Sans and Liberation Sans all work)."
    )


def _supports_turkish(font_path: Path) -> bool:
    try:
        font = fitz.Font(fontfile=str(font_path))
    except Exception:
        return False
    return all(font.has_glyph(ord(char)) for char in TURKISH_PROBE)


def _build_html(text: str) -> str:
    """Notarial-looking layout: a centred heading, then justified paragraphs."""
    blocks = [block.strip() for block in text.replace("\r\n", "\n").split("\n\n")]
    blocks = [block for block in blocks if block]
    if not blocks:
        raise RenderError("source text is empty")

    heading, *body = blocks
    parts = [f'<h1 class="baslik">{escape(heading)}</h1>']
    for block in body:
        parts.append(f"<p>{escape(block).replace(chr(10), '<br/>')}</p>")
    return "<div>" + "".join(parts) + "</div>"


def _css(font_path: Path) -> str:
    return f"""
@font-face {{ font-family: belge; src: url({font_path.name}); }}
* {{ font-family: belge; }}
div {{ font-size: 10.5px; line-height: 1.6; color: #2b3543; }}
h1.baslik {{ font-size: 12px; text-align: center; letter-spacing: 1.4px;
             margin: 0 0 18px 0; font-weight: bold; }}
p {{ text-align: justify; margin: 0 0 10px 0; }}
"""


def render(source: Path, pdf_path: Path, pages_dir: Path, font_path: Path) -> int:
    """Render one source text. Returns the page count."""
    text = source.read_text(encoding="utf-8")

    archive = fitz.Archive(str(font_path.parent))
    story = fitz.Story(html=_build_html(text), user_css=_css(font_path), archive=archive)

    content_rect = PAGE_SIZE + (MARGIN, MARGIN, -MARGIN, -MARGIN)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    writer = fitz.DocumentWriter(str(pdf_path))
    pages = 0
    more = True
    while more:
        device = writer.begin_page(PAGE_SIZE)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages > 40:  # pragma: no cover - runaway guard
            writer.close()
            raise RenderError(f"{source.name}: exceeded 40 pages; check the source text")
    writer.close()

    document = fitz.open(str(pdf_path))
    pages_dir.mkdir(parents=True, exist_ok=True)
    for existing in pages_dir.glob("page-*.png"):
        existing.unlink()
    matrix = fitz.Matrix(PNG_ZOOM, PNG_ZOOM)
    for index, page in enumerate(document, start=1):
        page.get_pixmap(matrix=matrix).save(str(pages_dir / f"page-{index}.png"))

    page_count = document.page_count
    document.close()
    return page_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", type=int, action="append", help="render only this case (repeatable)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--font", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.source.is_dir():
        print(
            f"Source directory {args.source} does not exist.\n"
            "The notarial Turkish text is an AI-engineer deliverable (GAP-10, due H2). "
            "Drop case1.txt … case4.txt there and re-run.",
            file=sys.stderr,
        )
        return 1

    wanted = set(args.case) if args.case else None
    sources = sorted(args.source.glob("case*.txt"))
    if wanted is not None:
        sources = [p for p in sources if int(p.stem.removeprefix("case")) in wanted]

    if not sources:
        print(f"No source texts found in {args.source} (expected case1.txt … case4.txt).", file=sys.stderr)
        return 1

    try:
        font_path = find_font(args.font)
    except RenderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"font: {font_path}")
    for source in sources:
        stem = source.stem
        try:
            pages = render(
                source,
                args.out / f"{stem}.pdf",
                args.out / "pages" / stem,
                font_path,
            )
        except RenderError as exc:
            print(f"  {stem}: {exc}", file=sys.stderr)
            return 3
        print(f"  {stem}: {pages} page(s) -> {args.out / f'{stem}.pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
