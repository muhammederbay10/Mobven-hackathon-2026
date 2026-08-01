# ai/tests/test_schema.py
"""Verifies frozen contracts and rejects malformed boundary payloads offline."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from ai.main import app
from ai.schema import (
    CHECK_IDS,
    AuthorityRule,
    CheckReport,
    CircularExtraction,
    ExtractionResult,
    PageMap,
    SignatoryRecord,
)


def extraction_example() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "document_id": "contract-check",
        "company": {
            "name": "ABC Teknoloji Ltd. Şti.",
            "taxNumber": "1234567890",
            "mersisNumber": "0123456789000017",
        },
        "notary": {
            "name": "1. Noterliği",
            "date": "2026-03-15",
            "yevmiye": "08912",
        },
        "validUntil": "2028-03-15",
        "representatives": [
            {
                "id": "rep-1",
                "name": "Ali Yılmaz",
                "nationalId": "123******01",
                "title": "Müdür",
                "mode": "SOLE",
                "coSigners": [],
                "limits": None,
            }
        ],
        "fieldsNeedingReview": [],
        "evidence": {
            "authorityClause": "Şirketi münferiden temsile yetkilidir.",
            "page": 1,
        },
        "rules": None,
    }


def report_example() -> dict[str, Any]:
    return {
        "verdict": "READY",
        "checks": [
            {
                "id": check_id.value,
                "status": "green",
                "title": f"Sözleşme kontrolü: {check_id.value}",
                "reason": "Sözleşme doğrulama örneği geçti.",
                "evidence": {},
            }
            for check_id in CHECK_IDS
        ],
    }


def test_extraction_result_accepts_frozen_contract() -> None:
    result = ExtractionResult.model_validate(extraction_example())

    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["schema_version"] == "1.0"
    assert payload["company"]["taxNumber"] == "1234567890"
    assert payload["representatives"][0]["coSigners"] == []
    assert payload["evidence"]["authorityClause"].startswith("Şirketi")


def test_representative_id_is_required_and_stable() -> None:
    payload = extraction_example()
    payload["representatives"][0]["id"] = "rep-1"

    result = ExtractionResult.model_validate(payload)

    assert result.representatives[0].id == "rep-1"

    del payload["representatives"][0]["id"]
    with pytest.raises(ValidationError, match="Field required"):
        ExtractionResult.model_validate(payload)


def test_money_fields_are_integer_kurus_not_float() -> None:
    payload = extraction_example()
    payload["representatives"][0]["limits"] = 50_000_000  # 500,000.00 TL

    result = ExtractionResult.model_validate(payload)

    assert result.representatives[0].limits == 50_000_000
    assert isinstance(result.representatives[0].limits, int)

    payload["representatives"][0]["limits"] = 500_000.5
    with pytest.raises(ValidationError, match="should be a valid integer"):
        ExtractionResult.model_validate(payload)


def test_extraction_rule_blocked_scope_carries_no_mode_or_cosigners() -> None:
    payload = extraction_example()
    payload["rules"] = [
        {
            "scope": "real_estate",
            "threshold": None,
            "mode": None,
            "coSigners": [],
            "blocked": True,
            "evidence": {"page": 1, "quote": "Gayrimenkul işlemleri kapsam dışıdır."},
        }
    ]

    result = ExtractionResult.model_validate(payload)
    assert result.rules[0].blocked is True
    assert result.rules[0].mode is None


def test_extraction_rule_blocked_with_mode_is_rejected() -> None:
    payload = extraction_example()
    payload["rules"] = [
        {
            "scope": "real_estate",
            "mode": "SOLE",
            "blocked": True,
            "evidence": {"page": 1, "quote": "Gayrimenkul işlemleri kapsam dışıdır."},
        }
    ]

    with pytest.raises(ValidationError, match="must not carry a mode"):
        ExtractionResult.model_validate(payload)


def test_extraction_rule_cosigners_reference_representative_ids() -> None:
    payload = extraction_example()
    payload["representatives"] = [
        {**payload["representatives"][0], "id": "rep-1"},
        {**payload["representatives"][0], "id": "rep-2", "name": "Ayşe Demir",
         "nationalId": "456******23"},
    ]
    payload["rules"] = [
        {
            "scope": "general",
            "mode": "JOINT",
            "coSigners": ["rep-1", "rep-2"],
            "evidence": {"page": 1, "quote": "Şirketi müştereken temsile yetkilidir."},
        }
    ]

    result = ExtractionResult.model_validate(payload)
    assert result.rules[0].co_signers == ["rep-1", "rep-2"]


def test_extraction_rule_cosigners_reject_unknown_representative_id() -> None:
    payload = extraction_example()
    payload["rules"] = [
        {
            "scope": "general",
            "mode": "JOINT",
            "coSigners": ["rep-1", "rep-99"],
            "evidence": {"page": 1, "quote": "Şirketi müştereken temsile yetkilidir."},
        }
    ]

    with pytest.raises(ValidationError, match="unknown representative id 'rep-99'"):
        ExtractionResult.model_validate(payload)


def test_extraction_rule_without_blocked_requires_mode() -> None:
    payload = extraction_example()
    payload["rules"] = [
        {
            "scope": "general",
            "evidence": {"page": 1, "quote": "Şirketi münferiden temsile yetkilidir."},
        }
    ]

    with pytest.raises(ValidationError, match="non-blocked rule requires a mode"):
        ExtractionResult.model_validate(payload)


def test_extraction_result_rejects_unknown_fields() -> None:
    payload = extraction_example()
    payload["unexpected"] = "contract drift"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExtractionResult.model_validate(payload)


def test_check_report_requires_all_nine_checks_in_order() -> None:
    payload = report_example()
    payload["checks"] = list(reversed(payload["checks"]))

    with pytest.raises(ValidationError, match="all nine frozen IDs in order"):
        CheckReport.model_validate(payload)


def test_check_report_rejects_unknown_check_id() -> None:
    payload = report_example()
    payload["checks"][0]["id"] = "invented_check"

    with pytest.raises(ValidationError, match="Input should be"):
        CheckReport.model_validate(payload)


def test_schema_version_is_string_everywhere() -> None:
    rule = AuthorityRule.model_validate(
        {
            "schema_version": "1.0",
            "who": {"type": "group", "ref": "A"},
            "sole_or_joint": "sole",
            "scope_text": "Genel işlemler",
            "source": "circular",
            "evidence": {"page": 1, "quote": "Genel işlemler"},
            "confidence": "high",
        }
    )

    assert rule.schema_version == "1.0"
    assert CircularExtraction.model_fields["schema_version"].default == "1.0"


def test_masked_national_id_requires_frozen_format() -> None:
    payload = extraction_example()
    payload["representatives"][0]["nationalId"] = "123***01"

    with pytest.raises(ValidationError, match="String should match pattern"):
        ExtractionResult.model_validate(payload)


def test_internal_signatory_uses_same_masked_id_format() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        SignatoryRecord.model_validate(
            {
                "id": "person-1",
                "name_printed": "Ali Yılmaz",
                "name_normalized": "ALI YILMAZ",
                "id_no_masked": "123***01",
            }
        )


def test_rule_reference_and_amount_range_are_validated() -> None:
    with pytest.raises(ValidationError, match="references require ref"):
        AuthorityRule.model_validate(
            {
                "who": {"type": "group"},
                "sole_or_joint": "sole",
                "amount_min": 500_000,
                "amount_max": 100_000,
                "scope_text": "Genel işlemler",
                "source": "circular",
                "evidence": {"page": 1, "quote": "Genel işlemler"},
                "confidence": "high",
            }
        )


def test_page_map_rejects_duplicate_or_unsorted_pages() -> None:
    with pytest.raises(ValidationError, match="ordered by page number"):
        PageMap.model_validate(
            {
                "pages": [
                    {"page": 2, "labels": ["rules"]},
                    {"page": 1, "labels": ["appointments"]},
                ]
            }
        )


@pytest.mark.asyncio
async def test_health_endpoint_uses_environment_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACTION_MODEL", "configured-test-model")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "engine": "configured-test-model",
        "schema_version": "1.0",
    }
