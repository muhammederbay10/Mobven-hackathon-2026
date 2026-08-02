"""Signature-circular upload and page rendering — task P1-02.

The browser supplies bytes and attestations; it never supplies a filesystem
path. Files are inspected by magic bytes, stored under a server-generated name,
rendered to PNG pages, and resolved beneath the configured data directory on
every read.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import fitz
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session

from api.config import Settings, get_settings, resolve_under
from api.errors import ApiError, not_found
from api.models import Application, AuditAction, AuditEntity, Document
from api.schemas import ApplicationStatus, ErrorCode
from api.services import application_service, audit_service

_SAFE_DISPLAY_NAME = re.compile(r"[\x00-\x1f\x7f]")


def store_document(
    session: Session,
    application: Application,
    *,
    file_bytes: bytes,
    original_filename: str | None,
    original_seen: bool,
    scanned_by: str,
    correlation_id: str,
    settings: Settings | None = None,
) -> Document:
    """Validate, store and render one document in the caller's transaction."""
    settings = settings or get_settings()

    if not original_seen:
        raise ApiError(
            ErrorCode.ATTESTATION_REQUIRED,
            "Belgenin aslı şubede görülmeden tarama kaydedilemez.",
            status_code=409,
        )
    if application.status is not ApplicationStatus.IDENTITY_VERIFIED:
        # Delegate the exact 409 contract to the shared state machine.
        application_service.transition(
            session,
            application,
            ApplicationStatus.DOCUMENT_SCANNED,
            correlation_id=correlation_id,
        )
    if not scanned_by.strip():
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Tarama işlemini yapan görevli belirtilmelidir.",
            status_code=422,
        )
    if not file_bytes:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Yüklenen belge boş olamaz.",
            status_code=422,
        )
    if len(file_bytes) > settings.max_upload_bytes:
        raise ApiError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            f"Belge en fazla {settings.max_upload_mb} MB olabilir.",
            status_code=413,
            details={"max_upload_mb": settings.max_upload_mb},
        )

    mime_type, extension = _inspect_media(file_bytes)
    page_count = _inspect_page_count(file_bytes, mime_type, settings.max_document_pages)
    digest = hashlib.sha256(file_bytes).hexdigest()

    token = uuid.uuid4().hex
    directory = resolve_under(settings.uploads_path, str(application.id), token)
    original_path = resolve_under(directory, f"original{extension}")
    pages_path = resolve_under(directory, "pages")

    try:
        directory.mkdir(parents=True, exist_ok=False)
        _atomic_write(original_path, file_bytes)
        pages_path.mkdir()
        _render_pages(file_bytes, mime_type, pages_path, page_count)
    except ApiError:
        _safe_remove_created_directory(directory, settings)
        raise
    except Exception as exc:
        _safe_remove_created_directory(directory, settings)
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Belge okunamadı veya sayfalara ayrılamadı.",
            status_code=422,
        ) from exc

    stored_path = original_path.relative_to(settings.data_path).as_posix()
    document = Document(
        application_id=application.id,
        stored_filename=original_path.name,
        original_filename=_display_filename(original_filename, extension),
        stored_path=stored_path,
        mime_type=mime_type,
        size_bytes=len(file_bytes),
        sha256=digest,
        page_count=page_count,
        original_seen=True,
        scanned_by=scanned_by.strip(),
    )

    try:
        session.add(document)
        session.flush()
        application_service.transition(
            session,
            application,
            ApplicationStatus.DOCUMENT_SCANNED,
            correlation_id=correlation_id,
        )
        audit_service.record_branch_action(
            session,
            action=AuditAction.DOCUMENT_UPLOADED,
            entity_type=AuditEntity.DOCUMENT,
            entity_id=document.id,
            correlation_id=correlation_id,
            detail={
                "application_id": application.id,
                "mime_type": mime_type,
                "size_bytes": len(file_bytes),
                "sha256": digest,
                "page_count": page_count,
                "original_filename": document.original_filename,
            },
        )
        audit_service.record_branch_action(
            session,
            action=AuditAction.ORIGINAL_ATTESTED,
            entity_type=AuditEntity.DOCUMENT,
            entity_id=document.id,
            correlation_id=correlation_id,
            detail={"application_id": application.id, "scanned_by": document.scanned_by},
        )
    except Exception:
        _safe_remove_created_directory(directory, settings)
        raise

    return document


def page_path(
    session: Session,
    document_id: int,
    page_number: int,
    settings: Settings | None = None,
) -> Path:
    """Resolve a rendered PNG by database identity, never by client path."""
    settings = settings or get_settings()
    document = session.get(Document, document_id)
    if document is None:
        raise not_found("Belge", document_id)
    if page_number < 1 or page_number > document.page_count:
        raise not_found("Belge sayfası", f"{document_id}/{page_number}")

    original = resolve_under(settings.data_path, document.stored_path)
    page = resolve_under(original.parent, "pages", f"page-{page_number}.png")
    if not page.is_file():
        raise not_found("Belge sayfası", f"{document_id}/{page_number}")
    return page


def _inspect_media(payload: bytes) -> tuple[str, str]:
    if payload.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    raise ApiError(
        ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        "Yalnızca PDF, PNG veya JPEG belgeleri yüklenebilir.",
        status_code=415,
    )


def _inspect_page_count(payload: bytes, mime_type: str, maximum: int) -> int:
    try:
        if mime_type == "application/pdf":
            with fitz.open(stream=payload, filetype="pdf") as document:
                if document.needs_pass:
                    raise ValueError("encrypted PDF")
                page_count = document.page_count
        else:
            with Image.open(_bytes_io(payload)) as image:
                image.verify()
            page_count = 1
    except (fitz.FileDataError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Belge dosyası bozuk, şifreli veya okunamıyor.",
            status_code=422,
        ) from exc

    if page_count < 1:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Belgede okunabilir bir sayfa bulunamadı.",
            status_code=422,
        )
    if page_count > maximum:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"Belge en fazla {maximum} sayfa olabilir.",
            status_code=422,
            details={"max_document_pages": maximum},
        )
    return page_count


def _render_pages(payload: bytes, mime_type: str, pages_path: Path, page_count: int) -> None:
    if mime_type == "application/pdf":
        with fitz.open(stream=payload, filetype="pdf") as document:
            matrix = fitz.Matrix(150 / 72, 150 / 72)
            for index, page in enumerate(document, start=1):
                target = resolve_under(pages_path, f"page-{index}.png")
                page.get_pixmap(matrix=matrix, alpha=False).save(str(target))
        return

    with Image.open(_bytes_io(payload)) as image:
        image.seek(0)
        normalized = image.convert("RGB")
        target = resolve_under(pages_path, "page-1.png")
        normalized.save(target, format="PNG")
    assert page_count == 1


def _atomic_write(path: Path, payload: bytes) -> None:
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".upload-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _display_filename(filename: str | None, extension: str) -> str:
    name = re.split(r"[\\/]", filename or "")[-1]
    name = _SAFE_DISPLAY_NAME.sub("", name).strip()
    return (name or f"belge{extension}")[:255]


def _safe_remove_created_directory(directory: Path, settings: Settings) -> None:
    safe = resolve_under(settings.uploads_path, directory.relative_to(settings.uploads_path))
    if safe.is_dir():
        shutil.rmtree(safe)


def _bytes_io(payload: bytes):
    from io import BytesIO

    return BytesIO(payload)
