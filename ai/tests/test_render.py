# ai/tests/test_render.py
"""Covers the dual-resolution render stage for PDF, image, and malformed inputs — offline."""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from ai.render import (
    DEFAULT_EXTRACT_DPI,
    DEFAULT_SORT_DPI,
    PageImages,
    UnreadableDocument,
    UnsupportedDocument,
    extract_dpi,
    render_document,
    render_path,
    sort_dpi,
)
from ai.scripts import check_render

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
A4_POINTS = (595, 842)


def make_pdf(pages: int, size: tuple[int, int] = A4_POINTS) -> bytes:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(*size)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_image(
    image_format: str = "PNG", size: tuple[int, int] = (1000, 1400), exif: bytes | None = None
) -> bytes:
    buffer = BytesIO()
    with Image.new("RGB", size, "white") as image:
        if exif is None:
            image.save(buffer, format=image_format)
        else:
            image.save(buffer, format=image_format, exif=exif)
    return buffer.getvalue()


def orientation_exif(value: int) -> bytes:
    exif = Image.Exif()
    exif[274] = value  # 274 = Orientation
    return exif.tobytes()


def test_pdf_renders_every_page_in_document_order() -> None:
    pages = render_document(make_pdf(3), "case1.pdf")

    assert [page.page_no for page in pages] == [1, 2, 3]
    assert all(isinstance(page, PageImages) for page in pages)


def test_pdf_pages_are_png_bytes_at_both_resolutions() -> None:
    page = render_document(make_pdf(1), "case1.pdf")[0]

    assert page.sort_png.startswith(PNG_MAGIC)
    assert page.extract_png.startswith(PNG_MAGIC)


def expected_size(dpi: int, points: tuple[int, int] = A4_POINTS) -> tuple[int, int]:
    """pdfium rounds a partial pixel up, so 595pt at 100 DPI is 827px, not 826."""

    return tuple(math.ceil(side / 72 * dpi) for side in points)


def test_the_extraction_image_is_larger_than_the_sorter_image() -> None:
    page = render_document(make_pdf(1), "case1.pdf")[0]

    assert page.extract_size[0] > page.sort_size[0]
    assert page.extract_size[1] > page.sort_size[1]
    assert len(page.extract_png) > len(page.sort_png)


def test_default_resolutions_match_the_documented_dpi() -> None:
    page = render_document(make_pdf(1), "case1.pdf")[0]

    assert page.sort_size == expected_size(DEFAULT_SORT_DPI)
    assert page.extract_size == expected_size(DEFAULT_EXTRACT_DPI)


def test_both_resolutions_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_DPI_SORT", "50")
    monkeypatch.setenv("PDF_DPI_EXTRACT", "150")

    assert (sort_dpi(), extract_dpi()) == (50, 150)

    page = render_document(make_pdf(1), "case1.pdf")[0]
    assert page.sort_size == expected_size(50)
    assert page.extract_size == expected_size(150)


def test_a_broken_dpi_setting_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_DPI_SORT", "yüz")
    monkeypatch.setenv("PDF_DPI_EXTRACT", "0")

    assert (sort_dpi(), extract_dpi()) == (DEFAULT_SORT_DPI, DEFAULT_EXTRACT_DPI)


def test_explicit_overrides_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_DPI_SORT", "50")

    page = render_document(make_pdf(1), "case1.pdf", sort=72, extract=72)[0]

    assert page.sort_size == page.extract_size == A4_POINTS


def test_rendering_the_same_bytes_twice_is_deterministic() -> None:
    data = make_pdf(2)

    first = render_document(data, "case1.pdf")
    second = render_document(data, "case1.pdf")

    assert [page.extract_png for page in first] == [page.extract_png for page in second]


@pytest.mark.parametrize(("image_format", "name"), [("PNG", "scan.png"), ("JPEG", "scan.jpg")])
def test_an_image_upload_is_a_single_page(image_format: str, name: str) -> None:
    pages = render_document(make_image(image_format), name)

    assert len(pages) == 1
    assert pages[0].page_no == 1
    assert pages[0].extract_size == (1000, 1400)


def test_the_sorter_copy_of_an_image_is_scaled_by_the_dpi_ratio() -> None:
    page = render_document(make_image("PNG", (1000, 1400)), "scan.png", sort=100, extract=250)[0]

    assert page.sort_size == (400, 560)


def test_a_photographed_page_is_rotated_upright() -> None:
    # Orientation 6 means "rotate 90°": without exif_transpose the model reads a sideways document.
    data = make_image("JPEG", (1000, 1400), exif=orientation_exif(6))

    page = render_document(data, "photo.jpg")[0]

    assert page.extract_size == (1400, 1000)


def test_content_wins_over_a_misleading_extension() -> None:
    pages = render_document(make_pdf(2), "scan.png")

    assert len(pages) == 2


def test_a_pdf_extension_without_a_pdf_header_is_unreadable() -> None:
    with pytest.raises(UnreadableDocument, match="no PDF header"):
        render_document(b"not a pdf at all", "scan.pdf")


def test_a_corrupt_pdf_is_unreadable() -> None:
    with pytest.raises(UnreadableDocument):
        render_document(b"%PDF-1.7\n%%EOF", "scan.pdf")


def test_a_corrupt_image_is_unreadable() -> None:
    with pytest.raises(UnreadableDocument):
        render_document(PNG_MAGIC + b"truncated", "scan.png")


def test_an_unsupported_file_type_is_rejected() -> None:
    with pytest.raises(UnsupportedDocument, match="unsupported file type"):
        render_document(b"plain text, no magic bytes", "notes.txt")


def test_an_unsupported_image_format_is_rejected() -> None:
    with pytest.raises(UnsupportedDocument, match="unsupported image format"):
        render_document(make_image("GIF"), "scan.gif")


def test_an_empty_upload_is_unreadable() -> None:
    with pytest.raises(UnreadableDocument, match="empty file"):
        render_document(b"", "scan.pdf")


def test_render_path_reads_a_file_from_disk(tmp_path: Path) -> None:
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(2))

    assert len(render_path(document)) == 2


def test_render_path_reports_a_missing_file_as_a_render_error(tmp_path: Path) -> None:
    with pytest.raises(UnreadableDocument, match="cannot read"):
        render_path(tmp_path / "absent.pdf")


def test_diagnostic_reports_a_rendered_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(2))

    exit_code = check_render.main([str(document)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "pages       2" in output
    assert "not written" in output


def test_diagnostic_reports_an_unreadable_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("plain text", encoding="utf-8")

    exit_code = check_render.main([str(document)])

    assert exit_code == 1
    assert "UnsupportedDocument" in capsys.readouterr().out


def test_diagnostic_writes_previews_on_request(tmp_path: Path) -> None:
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(2))
    previews = tmp_path / "previews"

    assert check_render.main([str(document), "--preview", str(previews)]) == 0
    assert len(list(previews.glob("*.png"))) == 4


def test_diagnostic_refuses_to_write_previews_into_stage_assets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(1))

    exit_code = check_render.main(
        [str(document), "--preview", str(check_render.STAGE_ASSETS / "documents")]
    )

    assert exit_code == 1
    assert "stage assets" in capsys.readouterr().out
