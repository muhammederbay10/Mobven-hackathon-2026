"""Phase 1-5 backend acceptance through the public HTTP surface."""

from __future__ import annotations

from pathlib import Path
import asyncio

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
ABC = "0123456789000017"


def _prepare(client: TestClient, case: int) -> int:
    application_id = client.post(f"/api/demo/load-case/{case}").json()["application_id"]
    source = 1 if case == 4 else case
    document = REPO_ROOT / "data" / "documents" / f"case{source}.pdf"
    response = client.post(
        f"/api/applications/{application_id}/document",
        files={"file": (document.name, document.read_bytes(), "application/pdf")},
        data={"original_seen": "true", "scanned_by": "kozyatagi01"},
    )
    assert response.status_code == 201, response.text
    return application_id


def test_all_four_offline_outcomes_are_persistent(client: TestClient) -> None:
    expected = {1: "READY", 2: "CO_SIGNER_REQUIRED", 3: "MISMATCH", 4: "REGISTRY_CONFLICT"}
    for case, verdict in expected.items():
        application_id = _prepare(client, case)
        analyzed = client.post(f"/api/applications/{application_id}/analyze")
        assert analyzed.status_code == 200, analyzed.text
        assert analyzed.json()["report"]["verdict"] == verdict
        restored = client.get(f"/api/applications/{application_id}").json()
        assert restored["application"]["status"] == "ANALYZED"
        assert restored["report"]["verdict"] == verdict


def test_analysis_response_reports_extraction_cache_hits(client: TestClient) -> None:
    first_application_id = _prepare(client, 1)
    first = client.post(f"/api/applications/{first_application_id}/analyze")
    assert first.status_code == 200
    assert first.headers["X-Extraction-Cache"] == "miss"

    second_application_id = _prepare(client, 1)
    second = client.post(f"/api/applications/{second_application_id}/analyze")
    assert second.status_code == 200
    assert second.headers["X-Extraction-Cache"] == "hit"


def test_corrections_approval_authorization_and_cosign(client: TestClient) -> None:
    application_id = _prepare(client, 1)
    assert client.post(f"/api/applications/{application_id}/analyze").status_code == 200

    corrected = client.patch(
        f"/api/applications/{application_id}/extraction",
        json={
            "reason": "Noter teyidi",
            "corrections": [
                {
                    "field_path": "validUntil",
                    "expected_old_value": "2029-01-15",
                    "new_value": "2029-01-16",
                }
            ],
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["extraction"]["validUntil"] == "2029-01-16"
    stale = client.patch(
        f"/api/applications/{application_id}/extraction",
        json={
            "reason": "Eski ekran",
            "corrections": [
                {
                    "field_path": "validUntil",
                    "expected_old_value": "2029-01-15",
                    "new_value": "2029-01-17",
                }
            ],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_CORRECTION"

    approved = client.post(
        f"/api/applications/{application_id}/decision", json={"action": "approve"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["application"]["status"] == "APPROVED"
    assert client.get(f"/api/authority/{ABC}").status_code == 200

    sole = client.post(
        "/api/transactions/authorize",
        json={
            "mersis": ABC,
            "subject": "GENERAL",
            "currency": "TRY",
            "amount_minor": 25000000,
            "initiator": "rep_abc_ali",
        },
    )
    assert sole.status_code == 200, sole.text
    assert sole.json()["verdict"] == "ALLOWED"
    assert sole.json()["authorization_code"].startswith("YTK-")

    joint = client.post(
        "/api/transactions/authorize",
        json={
            "mersis": ABC,
            "subject": "GENERAL",
            "currency": "TRY",
            "amount_minor": 120000000,
            "initiator": "rep_abc_ali",
        },
    )
    assert joint.status_code == 200, joint.text
    assert joint.json()["verdict"] == "PENDING_COSIGN"
    assert joint.json()["required_cosigner"] == "rep_abc_ayse"
    transaction_id = joint.json()["transaction_id"]
    completed = client.post(
        f"/api/transactions/{transaction_id}/cosign", json={"cosigner": "rep_abc_ayse"}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["verdict"] == "ALLOWED"
    repeated = client.post(
        f"/api/transactions/{transaction_id}/cosign", json={"cosigner": "rep_abc_ayse"}
    )
    assert repeated.json()["authorization_code"] == completed.json()["authorization_code"]

    credit = client.post(
        "/api/transactions/authorize",
        json={
            "mersis": ABC,
            "subject": "CREDIT",
            "currency": "TRY",
            "amount_minor": 75000000,
            "initiator": "rep_abc_ali",
        },
    )
    assert credit.status_code == 200
    assert credit.json()["verdict"] == "PENDING_COSIGN"
    assert client.post(
        f"/api/transactions/{credit.json()['transaction_id']}/cosign",
        json={"cosigner": "rep_abc_ayse"},
    ).json()["verdict"] == "ALLOWED"

    denied = client.post(
        "/api/transactions/authorize",
        json={
            "mersis": ABC,
            "subject": "REAL_ESTATE",
            "currency": "TRY",
            "amount_minor": 0,
            "initiator": "rep_abc_ali",
        },
    )
    assert denied.status_code == 200
    assert denied.json()["verdict"] == "DENIED"

    removed = client.put(
        f"/api/registry/{ABC}/reps/rep_abc_ali", json={"status": "REMOVED"}
    )
    assert removed.status_code == 200
    rechecked = client.post(
        "/api/transactions/authorize",
        json={
            "mersis": ABC,
            "subject": "GENERAL",
            "currency": "TRY",
            "amount_minor": 25000000,
            "initiator": "rep_abc_ali",
        },
    )
    assert rechecked.status_code == 200
    assert rechecked.json()["verdict"] == "DENIED"
    assert client.get(f"/api/authority/{ABC}").json()["status"] == "ACTIVE"
    assert len(client.get(f"/api/transactions?mersis={ABC}").json()) == 5


def test_internal_ai_diagnostics_and_unmatched_document_people_do_not_block_approval(
    client: TestClient,
) -> None:
    """Raw extraction stays complete; only active registry matches become authority people."""
    from copy import deepcopy

    from sqlmodel import Session, select

    from api.db import get_engine
    from api.models import Document, Extraction

    application_id = _prepare(client, 1)
    assert client.post(f"/api/applications/{application_id}/analyze").status_code == 200

    with Session(get_engine()) as session:
        document = session.exec(
            select(Document).where(Document.application_id == application_id)
        ).one()
        extraction = session.exec(
            select(Extraction).where(Extraction.document_id == document.id)
        ).one()
        payload = deepcopy(extraction.payload)
        payload["fieldsNeedingReview"] = ["raw_chunks[3].output.rules[10].joint_with"]
        payload["representatives"].append(
            {
                "id": "rep-extra",
                "name": "Belgede Kalan Kişi",
                "nameNormalized": "belgede kalan kisi",
                "nationalId": "999******99",
                "title": "Temsilci",
                "mode": "SOLE",
                "coSigners": [],
                "limits": None,
            }
        )
        extraction.payload = payload
        session.add(extraction)
        session.commit()

    approved = client.post(
        f"/api/applications/{application_id}/decision",
        json={"action": "approve"},
    )
    assert approved.status_code == 200, approved.text
    authority_names = {person["name"] for person in approved.json()["authority"]["persons"]}
    assert "Belgede Kalan Kişi" not in authority_names


def test_missing_document_wrong_state_and_cache_controls(client: TestClient) -> None:
    application_id = client.post("/api/demo/load-case/1").json()["application_id"]
    missing = client.post(f"/api/applications/{application_id}/analyze")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "DOCUMENT_REQUIRED"
    wrong = client.post(
        f"/api/applications/{application_id}/decision", json={"action": "approve"}
    )
    assert wrong.status_code == 409
    warmed = client.post("/api/demo/cache/prewarm")
    assert warmed.status_code == 200
    assert warmed.json()["count"] == 3
    assert client.post("/api/demo/cache/clear").status_code == 200


def test_ai_timeout_is_recoverable_and_raw_extraction_stays_immutable(
    client: TestClient, demo_env
) -> None:
    from sqlmodel import Session, select

    from api.db import get_engine
    from api.models import Application, Extraction
    from api.services import ai_client, analysis_service

    application_id = _prepare(client, 1)

    class FailingClient:
        engine = "failing-test"

        async def health(self):
            return False

        async def extract(self, **_kwargs):
            raise ai_client.ai_timeout_error(0.01)

        async def analyze(self, _request):
            raise AssertionError("analyze must not run after extract failure")

    with Session(get_engine()) as session:
        try:
            asyncio.run(
                analysis_service.analyze_application(
                    session,
                    application_id,
                    correlation_id="timeout-test",
                    settings=demo_env,
                    client=FailingClient(),
                )
            )
        except Exception as exc:
            assert getattr(exc, "code", None).value == "AI_TIMEOUT"
        else:
            raise AssertionError("timeout was not surfaced")
    with Session(get_engine()) as session:
        assert session.get(Application, application_id).status.value == "ANALYSIS_FAILED"
        assert session.exec(select(Extraction)).all() == []

    assert client.post(f"/api/applications/{application_id}/analyze").status_code == 200
    corrected = client.patch(
        f"/api/applications/{application_id}/extraction",
        json={
            "reason": "Tarih teyidi",
            "corrections": [{
                "field_path": "validUntil",
                "expected_old_value": "2029-01-15",
                "new_value": "2029-01-16",
            }],
        },
    )
    assert corrected.status_code == 200
    with Session(get_engine()) as session:
        raw = session.exec(select(Extraction)).one()
        assert raw.payload["validUntil"] == "2029-01-15"


def test_override_versioning_and_cosign_guards(client: TestClient) -> None:
    case_two = _prepare(client, 2)
    assert client.post(f"/api/applications/{case_two}/analyze").status_code == 200
    missing_override = client.post(
        f"/api/applications/{case_two}/decision", json={"action": "approve"}
    )
    assert missing_override.status_code == 422
    approved = client.post(
        f"/api/applications/{case_two}/decision",
        json={"action": "approve", "override_justification": "Müşterek imza mobilde alınacak."},
    )
    assert approved.status_code == 200, approved.text

    pending = client.post(
        "/api/transactions/authorize",
        json={
            "mersis": ABC,
            "subject": "GENERAL",
            "currency": "TRY",
            "amount_minor": 100,
            "initiator": "rep_abc_ali",
        },
    ).json()
    assert pending["verdict"] == "PENDING_COSIGN"
    assert client.post(
        f"/api/transactions/{pending['transaction_id']}/cosign",
        json={"cosigner": "rep_abc_ali"},
    ).status_code == 409
    assert client.post(
        f"/api/transactions/{pending['transaction_id']}/cosign",
        json={"cosigner": "rep_zeta_kemal"},
    ).status_code == 409
    client.put(f"/api/registry/{ABC}/reps/rep_abc_ayse", json={"status": "REMOVED"})
    removed = client.post(
        f"/api/transactions/{pending['transaction_id']}/cosign",
        json={"cosigner": "rep_abc_ayse"},
    )
    assert removed.status_code == 200
    assert removed.json()["verdict"] == "DENIED"
    assert removed.json()["authorization_code"] is None

    client.put(f"/api/registry/{ABC}/reps/rep_abc_ayse", json={"status": "ACTIVE"})
    case_one = _prepare(client, 1)
    assert client.post(f"/api/applications/{case_one}/analyze").status_code == 200
    assert client.post(
        f"/api/applications/{case_one}/decision", json={"action": "approve"}
    ).status_code == 200
    versions = client.get(f"/api/authority/{ABC}/history").json()["items"]
    assert [item["version"] for item in versions] == [2, 1]
    assert [item["status"] for item in versions] == ["ACTIVE", "SUSPENDED"]
