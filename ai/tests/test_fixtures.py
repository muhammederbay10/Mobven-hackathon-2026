# ai/tests/test_fixtures.py
"""Guards the four demo fixtures: schema validity, verbatim evidence, and expected verdicts."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai.schema import CheckId, CheckStatus, CheckVerdict, ExtractionResult
from ai.scripts.check_fixtures import (
    CASE_NUMBERS,
    FIXTURES_DIR,
    REPO_ROOT,
    CaseReport,
    check_case,
    check_extraction,
    check_shared_document,
    expected_path,
    extraction_path,
    main,
    verdict_from_statuses,
)

# The demo script decides these, not the fixtures — if a fixture edit flips one, this test fails.
PLANNED_VERDICTS = {
    1: CheckVerdict.READY,
    2: CheckVerdict.CO_SIGNER_REQUIRED,
    3: CheckVerdict.MISMATCH,
    4: CheckVerdict.REGISTRY_CONFLICT,
}


def load_case(case: int) -> dict[str, Any]:
    return json.loads(extraction_path(case).read_text(encoding="utf-8"))


def load_expected(case: int) -> dict[str, Any]:
    return json.loads(expected_path(case).read_text(encoding="utf-8"))


def copy_fixtures(destination: Path) -> Path:
    for path in FIXTURES_DIR.glob("case*.json"):
        shutil.copy(path, destination / path.name)
    return destination


def rewrite(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def collapse(text: str) -> str:
    """Line wrapping in the document markdown must not break verbatim quote matching."""

    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_fixture_passes_every_diagnostic(case: int) -> None:
    report = check_case(case)

    assert report.problems == []


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_fixture_validates_as_extraction_result(case: int) -> None:
    extraction = ExtractionResult.model_validate(load_case(case))

    assert extraction.schema_version == "1.0"
    assert extraction.representatives
    assert extraction.evidence.authority_clause.strip()


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_expected_verdict_matches_the_demo_script(case: int) -> None:
    expected = load_expected(case)

    assert CheckVerdict(expected["expected_verdict"]) is PLANNED_VERDICTS[case]


@pytest.mark.parametrize("case", CASE_NUMBERS)
def test_evidence_is_verbatim_from_the_document_copy(case: int) -> None:
    expected = load_expected(case)
    document = collapse((REPO_ROOT / expected["document"]).read_text(encoding="utf-8"))
    extraction = ExtractionResult.model_validate(load_case(case))

    assert collapse(extraction.evidence.authority_clause) in document
    for rule in extraction.rules or []:
        assert collapse(rule.evidence.quote) in document


def test_case_four_is_the_same_document_as_case_one() -> None:
    assert check_shared_document() == []
    assert load_case(4) == load_case(1)
    assert load_case(4)["document_id"] == "doc_01"


def test_case_four_differs_from_case_one_only_in_the_registry() -> None:
    first, fourth = load_expected(1), load_expected(4)

    assert first["application"] == fourth["application"]
    assert first["registry"] != fourth["registry"]
    reps = {rep["name"]: rep["status"] for rep in fourth["registry"]["0123456789000017"]["reps"]}
    assert reps["Ali Yılmaz"] == "REMOVED"


def test_corrupted_fixture_fails_validation() -> None:
    payload = load_case(1)
    payload["representatives"][0]["nationalId"] = "12345678901"

    with pytest.raises(ValidationError, match="String should match pattern"):
        ExtractionResult.model_validate(payload)


def test_corrupted_fixture_is_reported_by_the_diagnostic() -> None:
    payload = load_case(1)
    payload["evidence"]["authorityClause"] = "   "
    report = CaseReport(case=1)

    check_extraction(payload, report)

    assert any("authorityClause" in problem for problem in report.problems)


def test_diagnostic_rejects_a_name_from_outside_the_demo_roster() -> None:
    payload = load_case(1)
    payload["representatives"][0]["name"] = "Tolga Akar"
    report = CaseReport(case=1)

    check_extraction(payload, report)

    assert any("fictional demo people" in problem for problem in report.problems)


def test_diagnostic_exits_nonzero_on_a_corrupted_extraction_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = copy_fixtures(tmp_path)
    payload = load_case(2)
    payload["representatives"][0]["mode"] = "ALONE"
    rewrite(extraction_path(2, fixtures), payload)

    exit_code = main(["--fixtures-dir", str(fixtures)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Input should be 'SOLE' or 'JOINT'" in output
    assert "FAILED — cases 2" in output


def test_diagnostic_exits_nonzero_when_an_expected_check_is_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = copy_fixtures(tmp_path)
    payload = load_expected(1)
    del payload["expected_checks"][4]
    rewrite(expected_path(1, fixtures), payload)

    exit_code = main(["--fixtures-dir", str(fixtures)])

    assert exit_code == 1
    assert "missing identity_match" in capsys.readouterr().out


def test_diagnostic_exits_nonzero_when_expected_checks_are_reordered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = copy_fixtures(tmp_path)
    payload = load_expected(3)
    payload["expected_checks"].reverse()
    rewrite(expected_path(3, fixtures), payload)

    exit_code = main(["--fixtures-dir", str(fixtures)])

    assert exit_code == 1
    assert "wrong order" in capsys.readouterr().out


def test_diagnostic_exits_zero_on_an_empty_fixture_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--fixtures-dir", str(tmp_path)])

    assert exit_code == 0
    assert "no fixtures found" in capsys.readouterr().out


def test_diagnostic_exits_zero_on_the_committed_fixtures(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "ALL FOUR FIXTURES VALID" in capsys.readouterr().out


def test_verdict_priority_is_mismatch_over_registry_over_cosigner() -> None:
    green = dict.fromkeys(CheckId, CheckStatus.GREEN)

    assert verdict_from_statuses(green) is CheckVerdict.READY

    cosigner = green | {CheckId.AUTHORITY_MODE: CheckStatus.AMBER}
    assert verdict_from_statuses(cosigner) is CheckVerdict.CO_SIGNER_REQUIRED

    registry = cosigner | {CheckId.REGISTRY_REPRESENTATIVE_MATCH: CheckStatus.RED}
    assert verdict_from_statuses(registry) is CheckVerdict.REGISTRY_CONFLICT

    mismatch = registry | {CheckId.COMPANY_NAME_MATCH: CheckStatus.RED}
    assert verdict_from_statuses(mismatch) is CheckVerdict.MISMATCH


def test_masked_ids_never_leak_a_full_national_id() -> None:
    for case in CASE_NUMBERS:
        for path in (extraction_path(case), expected_path(case)):
            text = path.read_text(encoding="utf-8")

            # 11 digits standing alone is a TCKN; the 16-digit MERSİS number is not a match.
            assert not re.search(r"(?<!\d)\d{11}(?!\d)", text), f"{path.name} leaks a full TCKN"


def test_fixture_directory_holds_exactly_the_eight_files() -> None:
    names = sorted(path.name for path in FIXTURES_DIR.glob("*.json"))

    assert names == sorted(
        [f"case{case}.json" for case in CASE_NUMBERS]
        + [f"case{case}.expected.json" for case in CASE_NUMBERS]
    )
