"""P1-02 application intake, document upload, rendering and aggregate API."""

from __future__ import annotations

import hashlib

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from api.config import Settings
from api.db import get_engine
from api.models import Application, AuditAction, AuditLog, Document
from api.schemas import ApplicationStatus


def application_payload(*, attested: bool = True) -> dict[str, object]:
    return {
        "company_name": "ABC Teknoloji Ltd. Şti.",
        "tax_number": "1234567890",
        "mersis": "0123456789000017",
        "applicant_name": "Ali Yılmaz",
        "applicant_tckn_masked": "123******01",
        "branch_code": "kozyatagi01",
        "identity_verified_at_branch": attested,
    }


def pdf_bytes(page_count: int = 2) -> bytes:
    document = fitz.open()
    for index in range(page_count):
        page = document.new_page()
        page.insert_text((72, 72), f"YetkiCheck synthetic page {index + 1}")
    payload = document.tobytes()
    document.close()
    return payload


def create_application(client: TestClient, *, attested: bool = True) -> dict[str, object]:
    response = client.post("/api/applications", json=application_payload(attested=attested))
    assert response.status_code == 201, response.text
    return response.json()


def upload_pdf(
    client: TestClient,
    application_id: int,
    payload: bytes,
    *,
    original_seen: bool = True,
    filename: str = "imza-sirkuleri.pdf",
):
    return client.post(
        f"/api/applications/{application_id}/document",
        files={"file": (filename, payload, "application/pdf")},
        data={"original_seen": str(original_seen).lower(), "scanned_by": "kozyatagi01"},
    )


def test_create_application_returns_the_persistent_resource(client: TestClient) -> None:
    body = create_application(client)
    assert body["status"] == "IDENTITY_VERIFIED"
    assert body["identity_verified_at_branch"] is True
    assert body["applicant_tckn_masked"] == "123******01"
    assert body["created_at"].endswith("Z")

    with Session(get_engine()) as session:
        application = session.get(Application, body["id"])
    assert application is not None
    assert application.status is ApplicationStatus.IDENTITY_VERIFIED


def test_application_without_identity_attestation_remains_draft(client: TestClient) -> None:
    body = create_application(client, attested=False)
    assert body["status"] == "DRAFT"


def test_unknown_keys_are_rejected_with_the_standard_error(client: TestClient) -> None:
    response = client.post(
        "/api/applications",
        json={**application_payload(), "case_number": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "case_number" in response.text


def test_upload_requires_original_document_attestation(client: TestClient) -> None:
    application = create_application(client)
    response = upload_pdf(client, int(application["id"]), pdf_bytes(), original_seen=False)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ATTESTATION_REQUIRED"


def test_upload_cannot_bypass_identity_attestation(client: TestClient) -> None:
    application = create_application(client, attested=False)
    response = upload_pdf(client, int(application["id"]), pdf_bytes())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_upload_rejects_unknown_media_by_magic_bytes(client: TestClient) -> None:
    application = create_application(client)
    response = upload_pdf(client, int(application["id"]), b"not actually a pdf")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_rejects_payload_over_the_configured_limit(
    client: TestClient, demo_env: Settings
) -> None:
    demo_env.max_upload_mb = 1
    application = create_application(client)
    response = upload_pdf(client, int(application["id"]), b"%PDF-" + b"x" * (1024 * 1024))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_rejects_too_many_pages(client: TestClient, demo_env: Settings) -> None:
    demo_env.max_document_pages = 1
    application = create_application(client)
    response = upload_pdf(client, int(application["id"]), pdf_bytes(2))
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"max_document_pages": 1}


def test_pdf_upload_hashes_renders_and_audits(
    client: TestClient, demo_env: Settings
) -> None:
    application = create_application(client)
    payload = pdf_bytes(2)
    response = upload_pdf(
        client,
        int(application["id"]),
        payload,
        filename=r"C:\fakepath\..\imza-sirkuleri.pdf",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["application_id"] == application["id"]
    assert body["mime_type"] == "application/pdf"
    assert body["document_sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["page_count"] == 2
    assert body["original_seen"] is True
    assert body["original_filename"] == "imza-sirkuleri.pdf"
    assert "stored_path" not in body

    with Session(get_engine()) as session:
        document = session.get(Document, body["id"])
        persisted_application = session.get(Application, application["id"])
        audit = session.exec(select(AuditLog).order_by(AuditLog.id)).all()
    assert document is not None
    stored = demo_env.data_path / document.stored_path
    assert stored.is_file()
    assert demo_env.uploads_path in stored.resolve().parents
    assert persisted_application is not None
    assert persisted_application.status is ApplicationStatus.DOCUMENT_SCANNED
    assert AuditAction.DOCUMENT_UPLOADED in [row.action for row in audit]
    assert AuditAction.ORIGINAL_ATTESTED in [row.action for row in audit]

    page = client.get(f"/api/documents/{body['id']}/page/1")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("image/png")
    assert page.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_document_page_validates_document_and_range(client: TestClient) -> None:
    missing_document = client.get("/api/documents/999/page/1")
    assert missing_document.status_code == 404
    assert missing_document.json()["error"]["code"] == "NOT_FOUND"

    application = create_application(client)
    uploaded = upload_pdf(client, int(application["id"]), pdf_bytes(1)).json()
    missing_page = client.get(f"/api/documents/{uploaded['id']}/page/2")
    assert missing_page.status_code == 404
    assert missing_page.json()["error"]["code"] == "NOT_FOUND"


def test_aggregate_restores_application_and_document_state(client: TestClient) -> None:
    application = create_application(client)
    uploaded = upload_pdf(client, int(application["id"]), pdf_bytes(1)).json()

    response = client.get(f"/api/applications/{application['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["application"]["status"] == "DOCUMENT_SCANNED"
    assert body["document"]["id"] == uploaded["id"]
    assert body["document"]["page_count"] == 1
    assert body["extraction"] is None
    assert body["report"] is None
    assert body["corrections"] == []
    assert body["authority"] is None


def test_missing_multipart_field_uses_the_standard_error(client: TestClient) -> None:
    application = create_application(client)
    response = client.post(
        f"/api/applications/{application['id']}/document",
        files={"file": ("scan.pdf", pdf_bytes(1), "application/pdf")},
        data={"scanned_by": "kozyatagi01"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_application_returns_controlled_404(client: TestClient) -> None:
    response = client.get("/api/applications/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
