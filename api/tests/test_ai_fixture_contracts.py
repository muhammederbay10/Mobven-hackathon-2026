"""Offline validation of the AI engineer's delivered flat-contract fixtures."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from api import schemas as s
from api.tests.conftest import (
    AI_FIXTURES_DIR,
    CASES_FILE,
    DATA_DIR,
    EXTRACTION_FIXTURES_DIR,
    REGISTRY_SEED_FILE,
    REPORT_FIXTURES_DIR,
    collect_json,
    load_json,
    require_delivered,
)

REP_ID = re.compile(r"^rep-\d+$")
UNMASKED_TCKN = re.compile(r"(?<!\d)\d{11}(?!\d)")


def _extractions() -> list[tuple[str, object]]:
    return [
        (label, body)
        for label, body in collect_json(AI_FIXTURES_DIR, EXTRACTION_FIXTURES_DIR)
        if isinstance(body, dict) and "representatives" in body
    ]


def _reports() -> list[tuple[str, object]]:
    return [
        (label, body)
        for label, body in collect_json(AI_FIXTURES_DIR, REPORT_FIXTURES_DIR)
        if isinstance(body, dict) and "checks" in body
    ]


def test_delivered_extractions_match_the_flat_wire_contract() -> None:
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")
    defects: list[str] = []
    for label, body in found:
        try:
            s.ExtractionResult.model_validate(body)
        except ValidationError as exc:
            defects.append(f"{label}: {exc}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_representative_ids_and_rule_references_are_stable() -> None:
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")
    defects: list[str] = []
    for label, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        known = {representative.id for representative in extraction.representatives}
        for representative in extraction.representatives:
            if not REP_ID.fullmatch(representative.id):
                defects.append(f"{label}: representative id {representative.id!r} is not rep-N")
        for rule in extraction.rules:
            unresolved = set(rule.co_signers) - known
            if unresolved:
                defects.append(f"{label}: unresolved rule coSigners {sorted(unresolved)}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_money_is_integer_kurus_and_blocked_rules_are_explicit() -> None:
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")
    defects: list[str] = []
    for label, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        for representative in extraction.representatives:
            if representative.limits is not None and not isinstance(representative.limits, int):
                defects.append(f"{label}: {representative.id}.limits is not integer kuruş")
        for rule in extraction.rules:
            if rule.threshold is not None and not isinstance(rule.threshold, int):
                defects.append(f"{label}: {rule.scope}.threshold is not integer kuruş")
            if rule.blocked and (rule.mode is not None or rule.co_signers):
                defects.append(f"{label}: blocked {rule.scope} rule carries signing authority")
        if not any(rule.scope == "real_estate" and rule.blocked for rule in extraction.rules):
            defects.append(f"{label}: missing explicit blocked real_estate rule")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_evidence_is_verbatim_and_page_numbers_are_positive() -> None:
    found = _extractions()
    require_delivered(found, "ExtractionResult fixtures")
    for _, body in found:
        extraction = s.ExtractionResult.model_validate(body)
        assert extraction.evidence.authority_clause.strip()
        assert extraction.evidence.page >= 1
        for rule in extraction.rules:
            assert rule.evidence.quote.strip()
            assert rule.evidence.page >= 1


def test_delivered_reports_match_the_nine_check_contract() -> None:
    found = _reports()
    require_delivered(found, "CheckReport fixtures")
    defects: list[str] = []
    for label, body in found:
        try:
            report = s.CheckReport.model_validate(body)
            assert [check.id for check in report.checks] == list(s.CHECK_IDS)
        except (ValidationError, AssertionError) as exc:
            defects.append(f"{label}: {exc}")
    assert not defects, "AI contract defects to hand back:\n" + "\n".join(defects)


def test_no_ai_fixture_contains_an_unmasked_tckn() -> None:
    found = _extractions() + _reports()
    require_delivered(found, "AI fixtures")
    defects = [
        f"{label}: contains an 11-digit run {match.group()!r}"
        for label, body in found
        for match in UNMASKED_TCKN.finditer(repr(body))
    ]
    assert not defects, "privacy defects to hand back:\n" + "\n".join(defects)


def test_registry_seed_matches_the_fixed_cast() -> None:
    registry = s.Registry.model_validate(load_json(REGISTRY_SEED_FILE))
    companies = {company.mersis: company for company in registry.companies}
    assert set(companies) == {"0123456789000017", "0987654321000023"}
    assert {rep.id: (rep.name, rep.tckn) for rep in companies["0123456789000017"].representatives} == {
        "rep_abc_ali": ("Ali Yılmaz", "123******01"),
        "rep_abc_ayse": ("Ayşe Demir", "987******45"),
    }
    for company in registry.companies:
        assert company.status is s.RegistryCompanyStatus.ACTIVE
        assert all(rep.status is s.RegistryRepresentativeStatus.ACTIVE for rep in company.representatives)


def test_no_committed_demo_data_contains_an_unmasked_tckn() -> None:
    defects = [
        f"{path.name}: contains an 11-digit run {match.group()!r}"
        for path in (REGISTRY_SEED_FILE, CASES_FILE)
        for match in UNMASKED_TCKN.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not defects, "\n".join(defects)


def test_clean_case_fixture_is_act_two_capable() -> None:
    case_one = [
        (label, body)
        for label, body in _extractions()
        if "case1" in label.replace("_", "").lower()
    ]
    require_delivered(case_one, "case 1 ExtractionResult fixture")
    extraction = s.ExtractionResult.model_validate(case_one[0][1])
    assert {"Ali Yılmaz", "Ayşe Demir"} <= {rep.name for rep in extraction.representatives}
    assert any(rule.threshold == 50_000_000 for rule in extraction.rules)
    assert any(rule.scope == "real_estate" and rule.blocked for rule in extraction.rules)


def test_case_documents_exist_once_rendered() -> None:
    cases = load_json(CASES_FILE)
    assert isinstance(cases, dict)
    referenced = sorted({case["document"] for case in cases["cases"]})
    missing = [name for name in referenced if not (DATA_DIR / "documents" / name).is_file()]
    if missing:
        pytest.skip(f"Documents not rendered yet: {missing}")
    assert all((DATA_DIR / "documents" / name).stat().st_size > 0 for name in referenced)
