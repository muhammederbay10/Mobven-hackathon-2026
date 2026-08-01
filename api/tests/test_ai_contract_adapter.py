"""Tests for the bank-to-AI boundary defined in docs/API_CONTRACT.md."""

from __future__ import annotations

import json

import httpx
import pytest

from api import schemas as s
from api.errors import ApiError
from api.services.ai_client import ExtractionCache, LiveAIServiceClient, build_analyze_request
from api.services.registry_service import load


def extraction_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_id": "doc-1",
        "company": {
            "name": "ABC Teknoloji Limited Şirketi",
            "taxNumber": "1234567890",
            "mersisNumber": "0123456789000017",
            "legalNameNormalized": "abc teknoloji",
        },
        "notary": {"name": "İstanbul 18. Noterliği", "date": "2026-03-15", "yevmiye": "08912"},
        "validUntil": "2028-03-15",
        "representatives": [
            {
                "id": "rep-1",
                "name": "Ali Yılmaz",
                "nameNormalized": "ali yilmaz",
                "nationalId": "123******01",
                "title": "Müdür",
                "mode": "SOLE",
                "coSigners": [],
                "limits": 50_000_000,
            }
        ],
        "fieldsNeedingReview": [],
        "evidence": {"authorityClause": "münferiden temsile yetkilidir", "page": 1},
        "rules": [
            {
                "scope": "real_estate",
                "threshold": None,
                "mode": None,
                "coSigners": [],
                "blocked": True,
                "evidence": {"page": 1, "quote": "gayrimenkul işlemleri kapsam dışıdır"},
            }
        ],
    }


def report_payload() -> dict[str, object]:
    return {
        "verdict": "READY",
        "checks": [
            {
                "id": check_id,
                "status": "green",
                "title": check_id,
                "reason": "kontrol edildi",
                "evidence": {},
            }
            for check_id in s.CHECK_IDS
        ],
    }


def test_flat_extraction_serializes_with_camel_case_aliases() -> None:
    extraction = s.ExtractionResult.model_validate(extraction_payload())
    dumped = extraction.model_dump(mode="json", by_alias=True)
    assert dumped["company"]["taxNumber"] == "1234567890"
    assert dumped["representatives"][0]["nationalId"] == "123******01"
    assert "tax_number" not in dumped["company"]
    assert dumped["rules"][0]["coSigners"] == []


def test_build_analyze_request_projects_the_bank_registry(demo_env) -> None:
    extraction = s.ExtractionResult.model_validate(extraction_payload())
    request = build_analyze_request(
        extraction=extraction,
        company_name="ABC Teknoloji Ltd. Şti.",
        tax_number="1234567890",
        mersis="0123456789000017",
        applicant_name="Ali Yılmaz",
        applicant_tckn_masked="123******01",
        branch_code="0341",
        identity_verified_at_branch=True,
        registry=load(demo_env),
        as_of="2026-08-01",
    ).model_dump(mode="json", by_alias=True)
    assert request["application"]["applicant_tckn"] == "123******01"
    assert request["registry"]["0123456789000017"]["name"] == "ABC Teknoloji Ltd. Şti."
    assert request["registry"]["0123456789000017"]["reps"][0]["name"] == "Ali Yılmaz"
    assert "companies" not in request["registry"]


@pytest.mark.asyncio
async def test_live_analyze_uses_the_flat_request_and_response(demo_env) -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=report_payload())

    client = LiveAIServiceClient(demo_env, transport=httpx.MockTransport(handler))
    extraction = s.ExtractionResult.model_validate(extraction_payload())
    request = build_analyze_request(
        extraction=extraction,
        company_name="ABC Teknoloji Ltd. Şti.",
        tax_number="1234567890",
        mersis="0123456789000017",
        applicant_name="Ali Yılmaz",
        applicant_tckn_masked="123******01",
        branch_code="0341",
        identity_verified_at_branch=True,
        registry=load(demo_env),
    )
    report = await client.analyze(request)
    assert report.verdict is s.OnboardingVerdict.READY
    assert seen["extraction"]["company"]["legalNameNormalized"] == "abc teknoloji"


def test_cache_metadata_is_bank_owned_and_wire_payload_stays_verbatim(demo_env) -> None:
    extraction = s.ExtractionResult.model_validate(extraction_payload())
    path = ExtractionCache(demo_env).put(
        extraction,
        document_sha256="a" * 64,
        engine="gpt-5.6-luna",
    )
    assert path is not None
    cached = json.loads(path.read_text(encoding="utf-8"))
    assert cached["document_id"] == "doc-1"
    assert cached["company"]["legalNameNormalized"] == "abc teknoloji"
    assert "engine" not in cached and "document_sha256" not in cached


@pytest.mark.asyncio
async def test_extract_fails_honestly_until_the_endpoint_is_delivered(demo_env) -> None:
    client = LiveAIServiceClient(demo_env)
    with pytest.raises(ApiError) as exc:
        await client.extract(file_bytes=b"%PDF", filename="case1.pdf", document_id=1)
    assert exc.value.code is s.ErrorCode.AI_UNAVAILABLE
