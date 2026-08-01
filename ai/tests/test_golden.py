# ai/tests/test_golden.py
"""Per demo case: the exact verdict and the exact nine statuses, entirely offline."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai.compare import AMBER_CHECKS, analyze
from ai.main import app
from ai.schema import CHECK_IDS, AnalyzeRequest, CheckId, CheckStatus, CheckVerdict
from ai.scripts.check_fixtures import CASE_NUMBERS, expected_path, extraction_path


def load(path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_payload(case: int) -> dict[str, Any]:
    expected = load(expected_path(case))
    return {
        "extraction": load(extraction_path(case)),
        "application": expected["application"],
        "registry": expected["registry"],
        "as_of": expected["as_of"],
    }


def build_request(case: int) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(build_payload(case))


def statuses(report) -> dict[CheckId, CheckStatus]:
    return {check.id: check.status for check in report.checks}


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_case_produces_the_expected_verdict(case: int) -> None:
    report = analyze(build_request(case))

    assert report.verdict is CheckVerdict(load(expected_path(case))["expected_verdict"])


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_case_produces_the_expected_nine_statuses(case: int) -> None:
    report = analyze(build_request(case))

    produced = [(check.id.value, check.status.value) for check in report.checks]
    assert produced == [
        (entry["id"], entry["status"]) for entry in load(expected_path(case))["expected_checks"]
    ]


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_every_check_carries_a_turkish_title_and_reason(case: int) -> None:
    report = analyze(build_request(case))

    assert [check.id for check in report.checks] == list(CHECK_IDS)
    for check in report.checks:
        assert check.title.strip()
        assert check.reason.strip().endswith((".", "…"))


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_only_the_authority_check_is_ever_amber(case: int) -> None:
    report = analyze(build_request(case))

    ambers = {check.id for check in report.checks if check.status is CheckStatus.AMBER}
    assert ambers <= AMBER_CHECKS


def test_case_two_names_the_missing_co_signer() -> None:
    report = analyze(build_request(2))

    authority = next(check for check in report.checks if check.id is CheckId.AUTHORITY_MODE)
    assert authority.status is CheckStatus.AMBER
    assert "Ayşe Demir" in authority.reason


def test_case_three_applicant_absence_is_red_not_amber() -> None:
    report = analyze(build_request(3))

    applicant = next(check for check in report.checks if check.id is CheckId.APPLICANT_IN_DOCUMENT)
    assert applicant.status is CheckStatus.RED
    assert report.verdict is CheckVerdict.MISMATCH


def test_case_four_flips_to_ready_when_the_registry_is_restored() -> None:
    payload = build_payload(4)
    for rep in payload["registry"]["0123456789000017"]["reps"]:
        rep["status"] = "ACTIVE"

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert report.verdict is CheckVerdict.READY


def test_case_one_flips_to_registry_conflict_when_the_registry_is_revoked() -> None:
    payload = build_payload(1)
    payload["registry"]["0123456789000017"]["reps"][0]["status"] = "REMOVED"

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert report.verdict is CheckVerdict.REGISTRY_CONFLICT
    reds = {check.id for check in report.checks if check.status is CheckStatus.RED}
    assert reds == {CheckId.REGISTRY_REPRESENTATIVE_MATCH}


def test_case_four_and_case_one_read_the_same_document() -> None:
    assert build_payload(4)["extraction"] == build_payload(1)["extraction"]
    assert build_payload(4)["application"] == build_payload(1)["application"]


def test_a_masked_id_match_cannot_make_identity_green() -> None:
    payload = build_payload(1)
    # A stranger who happens to share Ali's visible digits: the document knows no such person.
    payload["application"]["applicant_name"] = "Veli Kaya"

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert statuses(report)[CheckId.IDENTITY_MATCH] is CheckStatus.RED
    assert statuses(report)[CheckId.APPLICANT_IN_DOCUMENT] is CheckStatus.RED
    assert report.verdict is CheckVerdict.MISMATCH


def test_a_name_match_with_a_different_masked_id_is_red() -> None:
    payload = build_payload(1)
    payload["application"]["applicant_tckn"] = "999******99"

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert statuses(report)[CheckId.APPLICANT_IN_DOCUMENT] is CheckStatus.GREEN
    assert statuses(report)[CheckId.IDENTITY_MATCH] is CheckStatus.RED


def test_an_expired_document_is_red() -> None:
    payload = build_payload(1)
    payload["as_of"] = "2029-01-01"

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert statuses(report)[CheckId.DOCUMENT_VALIDITY] is CheckStatus.RED
    assert report.verdict is CheckVerdict.MISMATCH


def test_a_document_without_a_validity_date_is_red() -> None:
    payload = build_payload(1)
    payload["extraction"]["validUntil"] = None

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert statuses(report)[CheckId.DOCUMENT_VALIDITY] is CheckStatus.RED
    assert report.verdict is CheckVerdict.MISMATCH


def test_missing_application_fields_cannot_produce_ready() -> None:
    payload = build_payload(1)
    payload["application"] = {}

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert report.verdict is not CheckVerdict.READY
    assert all(check.status is not CheckStatus.GREEN for check in report.checks[:6])


def test_an_unknown_company_is_a_registry_conflict() -> None:
    payload = build_payload(1)
    payload["registry"] = {}

    report = analyze(AnalyzeRequest.model_validate(payload))

    assert report.verdict is CheckVerdict.REGISTRY_CONFLICT
    assert statuses(report)[CheckId.REGISTRY_STATUS] is CheckStatus.RED


def test_analysis_does_not_mutate_its_input() -> None:
    request = build_request(1)
    before = deepcopy(request.model_dump(mode="json"))

    analyze(request)

    assert request.model_dump(mode="json") == before


def test_diagnostic_reports_every_case_as_matching(capsys: pytest.CaptureFixture[str]) -> None:
    from ai.scripts.check_analyze import main

    assert main(["--all"]) == 0
    assert main(["--case", "3"]) == 0
    assert "ALL EXPECTATIONS MET" in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASE_NUMBERS)
async def test_analyze_endpoint_returns_the_golden_report(case: int) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze", json=build_payload(case))

    body = response.json()
    assert response.status_code == 200
    assert body["verdict"] == load(expected_path(case))["expected_verdict"]
    assert [check["id"] for check in body["checks"]] == [check_id.value for check_id in CHECK_IDS]


@pytest.mark.asyncio
async def test_analyze_endpoint_degrades_instead_of_rejecting_a_malformed_body() -> None:
    payload = build_payload(1)
    payload["extraction"]["validUntil"] = "31.02.2026"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert body["verdict"] == CheckVerdict.MISMATCH.value
    assert {check["status"] for check in body["checks"]} == {"red"}
    assert "validUntil" in body["checks"][0]["reason"]


@pytest.mark.asyncio
async def test_analyze_endpoint_degrades_on_an_empty_body() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze", json={})

    body = response.json()
    assert response.status_code == 200
    assert body["verdict"] == CheckVerdict.MISMATCH.value
    assert len(body["checks"]) == 9
