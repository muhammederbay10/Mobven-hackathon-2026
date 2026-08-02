"""HTTP surface: health, readiness, demo control and the error envelope.

Plan sections 5.7, 8.1, 8.2 and 14. Nothing here reaches the network — the AI
service is never contacted, because the fixture runs in `AI_MODE=stub`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import Settings, get_settings
from api.db import reset_engine


# ---------------------------------------------------------------------------
# Infrastructure — section 8.1
# ---------------------------------------------------------------------------


def test_health_reports_process_and_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}


def test_health_does_not_require_the_ai_service(client: TestClient) -> None:
    """Section 8.1: an AI outage must not make the bank API look unhealthy.

    The fixture points AI_URL at a port nothing is listening on; /health must
    still be 200, because stub and replay modes work with the AI service stopped.
    """
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "ai" not in body


def test_ready_reports_database_data_dir_and_ai_mode(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["blocking"] == []
    assert body["checks"]["database"] is True
    assert body["checks"]["data_dir"] is True
    assert body["checks"]["registry_seed"] is True
    assert body["checks"]["cases_fixture"] is True
    assert body["checks"]["ai"]["ai_mode"] == "stub"
    # Reachability is *reported*, never owned: in stub mode it does not apply.
    assert body["checks"]["ai"]["reachable"] is None


def test_ready_is_503_when_committed_demo_input_is_missing(
    client: TestClient, demo_env: Settings
) -> None:
    demo_env.registry_seed_path.unlink()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["blocking"] == ["registry_seed"]


def test_every_response_carries_a_correlation_id(client: TestClient) -> None:
    """Section 15: every request receives a correlation ID."""
    response = client.get("/health")
    assert response.headers["X-Correlation-Id"]


# ---------------------------------------------------------------------------
# Demo control — section 8.2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_number", [1, 2, 3, 4])
def test_load_case_returns_201_and_an_application_id(
    client: TestClient, case_number: int
) -> None:
    response = client.post(f"/api/demo/load-case/{case_number}")
    assert response.status_code == 201
    assert isinstance(response.json()["application_id"], int)


def test_load_case_persists_across_requests(client: TestClient) -> None:
    first = client.post("/api/demo/load-case/1").json()["application_id"]
    second = client.post("/api/demo/load-case/1").json()["application_id"]
    assert second != first  # each load is its own application, not a reused row


def test_unknown_case_returns_the_standard_error_body(client: TestClient) -> None:
    response = client.post("/api/demo/load-case/99")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {
        "code",
        "message",
        "retryable",
        "details",
        "correlation_id",
    }
    assert body["error"]["code"] == "UNKNOWN_CASE"
    assert body["error"]["retryable"] is False
    # Section 5.7: no stack traces, raw payloads, local paths or secrets.
    assert "Traceback" not in response.text
    assert "api\\services" not in response.text and "api/services" not in response.text


def test_reset_returns_ok(client: TestClient) -> None:
    client.post("/api/demo/load-case/1")
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_no_response_body_leaks_a_local_filesystem_path(client: TestClient) -> None:
    """Section 5.7 keeps local paths out of responses; diagnostics are no exception."""
    bodies = [
        client.get("/health").text,
        client.get("/ready").text,
        client.get("/api/demo/cases").text,
        client.post("/api/demo/load-case/1").text,
        client.post("/api/demo/reset").text,
        client.post("/api/demo/load-case/99").text,
    ]
    for body in bodies:
        assert "C:\\\\" not in body and "C:/" not in body, body[:200]
        assert "/Users/" not in body and "\\\\Users\\\\" not in body, body[:200]
        assert "site-packages" not in body


def test_case_list_carries_titles_and_expected_outcomes(client: TestClient) -> None:
    """Plan section 10.2: four case cards with expected outcome labels."""
    cases = client.get("/api/demo/cases").json()["cases"]
    assert [case["case"] for case in cases] == [1, 2, 3, 4]
    assert [case["expected_verdict"] for case in cases] == [
        "READY",
        "CO_SIGNER_REQUIRED",
        "MISMATCH",
        "REGISTRY_CONFLICT",
    ]
    assert all(case["title"] and case["description"] for case in cases)


# ---------------------------------------------------------------------------
# DEMO_MODE guard — section 14
# ---------------------------------------------------------------------------


def test_demo_mutations_are_refused_when_demo_mode_is_off(
    demo_env: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    reset_engine()

    from api.main import create_app

    with TestClient(create_app()) as guarded:
        for method, path in (
            ("post", "/api/demo/load-case/1"),
            ("post", "/api/demo/reset"),
            ("post", "/api/demo/cache/prewarm"),
            ("post", "/api/demo/cache/clear"),
        ):
            response = getattr(guarded, method)(path)
            assert response.status_code == 403, path
            assert response.json()["error"]["code"] == "DEMO_MODE_DISABLED"

        registry_mutation = guarded.put(
            "/api/registry/0123456789000017/reps/rep_abc_ali",
            json={"status": "REMOVED"},
        )
        assert registry_mutation.status_code == 403
        assert registry_mutation.json()["error"]["code"] == "DEMO_MODE_DISABLED"

        # Health and readiness stay available — the guard is on mutations only.
        assert guarded.get("/health").status_code == 200

    get_settings.cache_clear()
    reset_engine()


# ---------------------------------------------------------------------------
# CORS — section 14
# ---------------------------------------------------------------------------


def test_cors_allows_the_configured_origin_only(client: TestClient) -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    exposed = allowed.headers.get("access-control-expose-headers", "")
    assert "X-Extraction-Cache" in exposed

    denied = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in denied.headers
