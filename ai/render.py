# ai/render.py
"""Renders PDF and image uploads into ordered page images at sorter and extraction resolutions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

DEFAULT_SORT_DPI = 100
DEFAULT_EXTRACT_DPI = 250
POINTS_PER_INCH = 72.0

PDF_MAGIC = b"%PDF-"
PDF_SUFFIX = ".pdf"
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
SUPPORTED_IMAGE_FORMATS = frozenset({"JPEG", "PNG"})


class RenderError(Exception):
    """Base for controlled rendering failures; the orchestrator turns these into review flags."""


class UnsupportedDocument(RenderError):
    """The file is not one of the formats a branch scanner produces."""


class UnreadableDocument(RenderError):
    """The format is supported but the bytes cannot be decoded."""


@dataclass(frozen=True)
class PageImages:
    """One document page at both resolutions. Page numbers are absolute and one-based."""

    page_no: int
    sort_png: bytes
    extract_png: bytes
    sort_size: tuple[int, int]
    extract_size: tuple[int, int]


def sort_dpi() -> int:
    return _dpi_from_env("PDF_DPI_SORT", DEFAULT_SORT_DPI)


def extract_dpi() -> int:
    return _dpi_from_env("PDF_DPI_EXTRACT", DEFAULT_EXTRACT_DPI)


def render_path(path: Path, **overrides: int | None) -> list[PageImages]:
    """Renders a file from disk. Diagnostics use this; the service renders uploaded bytes."""

    try:
        data = path.read_bytes()
    except OSError as error:
        raise UnreadableDocument(f"cannot read {path.name}: {error}") from error
    return render_document(data, path.name, **overrides)


def render_document(
    data: bytes,
    filename: str | None = None,
    *,
    sort: int | None = None,
    extract: int | None = None,
) -> list[PageImages]:
    """Renders an upload into ordered page images, one entry per page, in document order."""

    low = sort or sort_dpi()
    high = extract or extract_dpi()
    if not data:
        raise UnreadableDocument("empty file")

    suffix = Path(filename or "").suffix.lower()
    if data.startswith(PDF_MAGIC):
        # Content wins over the extension: a scanner that names a JPEG ".pdf" must still render.
        return _render_pdf(data, low, high)
    if suffix == PDF_SUFFIX:
        raise UnreadableDocument("file claims to be a PDF but has no PDF header")
    return _render_image(data, low, high, suffix)


def _dpi_from_env(name: str, default: int) -> int:
    """Reads a DPI knob at call time so tests and the demo can change it without a restart."""

    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _render_pdf(data: bytes, low: int, high: int) -> list[PageImages]:
    # Loop copied out of extraction-spike/test_extraction.py::render_pdf_pages (proven, frozen).
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        raise UnreadableDocument(f"PDF could not be opened: {error}") from error

    pages: list[PageImages] = []
    try:
        page_count = len(document)
        if page_count == 0:
            raise UnreadableDocument("PDF contains no pages")
        for index in range(page_count):
            page = document[index]
            try:
                sort_png, sort_size = _render_pdf_page(page, low)
                extract_png, extract_size = _render_pdf_page(page, high)
            finally:
                page.close()
            pages.append(
                PageImages(
                    page_no=index + 1,
                    sort_png=sort_png,
                    extract_png=extract_png,
                    sort_size=sort_size,
                    extract_size=extract_size,
                )
            )
    except pdfium.PdfiumError as error:
        raise UnreadableDocument(f"PDF page could not be rendered: {error}") from error
    finally:
        document.close()
    return pages


def _render_pdf_page(page: pdfium.PdfPage, dpi: int) -> tuple[bytes, tuple[int, int]]:
    bitmap = page.render(scale=dpi / POINTS_PER_INCH)
    image = bitmap.to_pil()
    try:
        return _encode_png(image), image.size
    finally:
        image.close()
        bitmap.close()


def _render_image(data: bytes, low: int, high: int, suffix: str) -> list[PageImages]:
    try:
        with Image.open(BytesIO(data)) as opened:
            if opened.format not in SUPPORTED_IMAGE_FORMATS:
                raise UnsupportedDocument(f"unsupported image format: {opened.format}")
            # A phone photo of a printed circular usually carries an EXIF rotation.
            upright = ImageOps.exif_transpose(opened)
    except UnidentifiedImageError as error:
        if suffix in IMAGE_SUFFIXES:
            raise UnreadableDocument(f"image could not be decoded: {error}") from error
        raise UnsupportedDocument(f"unsupported file type: {suffix or 'unknown'}") from error
    except OSError as error:
        raise UnreadableDocument(f"image could not be decoded: {error}") from error

    try:
        extract_png = _encode_png(upright)
        with _downscale(upright, low / high) as small:
            sort_png = _encode_png(small)
            sort_size = small.size
        return [
            PageImages(
                page_no=1,
                sort_png=sort_png,
                extract_png=extract_png,
                sort_size=sort_size,
                extract_size=upright.size,
            )
        ]
    finally:
        upright.close()


def _downscale(image: Image.Image, ratio: float) -> Image.Image:
    width, height = image.size
    size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    return image.resize(size, Image.LANCZOS)


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    with image.convert("RGB") as rgb:
        rgb.save(buffer, format="PNG")
    return buffer.getvalue()
