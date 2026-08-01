# ai/scripts/check_fixtures.py
"""Validates the four demo fixtures against ai/schema.py and prints each case's expected outcome."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import TypeAdapter, ValidationError  # noqa: E402

from ai.compare import analyze, verdict_from_statuses  # noqa: E402
from ai.schema import (  # noqa: E402
    CHECK_IDS,
    AnalyzeRequest,
    CheckId,
    CheckReport,
    CheckStatus,
    CheckVerdict,
    ExtractionResult,
    MaskedNationalId,
)

FIXTURES_DIR = REPO_ROOT / "ai" / "tests" / "fixtures"
CASE_NUMBERS = (1, 2, 3, 4)
EXPECTED_SUFFIX = ".expected.json"
REPORT_SUFFIX = "-report.json"

# Case 4 is case 1's document: the paper is genuine, only the registry differs.
SHARED_DOCUMENT_CASES = (1, 4)

# Whitelist, not a blacklist: a name from the frozen spike outputs must fail this, and we do not
# keep a list of real people anywhere in the repo to compare against.
DEMO_PEOPLE = frozenset({"Ali Yılmaz", "Ayşe Demir", "Kemal Öz", "Mehmet Kaya"})

MASKED_ID = TypeAdapter(MaskedNationalId)


@dataclass
class CaseReport:
    """Everything the script prints for one case, plus why it failed."""

    case: int
    problems: list[str] = field(default_factory=list)
    extraction: ExtractionResult | None = None
    expected: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


def extraction_path(case: int, fixtures_dir: Path = FIXTURES_DIR) -> Path:
    return fixtures_dir / f"case{case}.json"


def expected_path(case: int, fixtures_dir: Path = FIXTURES_DIR) -> Path:
    return fixtures_dir / f"case{case}{EXPECTED_SUFFIX}"


def report_path(case: int, fixtures_dir: Path = FIXTURES_DIR) -> Path:
    return fixtures_dir / f"case{case}{REPORT_SUFFIX}"


def discover_cases(fixtures_dir: Path = FIXTURES_DIR) -> list[int]:
    """Case numbers that have an extraction fixture on disk, expected files excluded."""

    cases = []
    for path in fixtures_dir.glob("case*.json"):
        if path.name.endswith(EXPECTED_SUFFIX):
            continue
        suffix = path.name[len("case") : -len(".json")]
        if suffix.isdigit():
            cases.append(int(suffix))
    return sorted(cases)


def load_json(path: Path, report: CaseReport) -> dict[str, Any] | None:
    if not path.exists():
        report.problems.append(f"missing file: {path.name}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report.problems.append(f"{path.name}: invalid JSON — {error}")
        return None


def check_masked_id(value: Any, where: str, report: CaseReport) -> None:
    try:
        MASKED_ID.validate_python(value)
    except ValidationError:
        report.problems.append(f"{where}: masked id must look like 123******01, got {value!r}")


def check_person_name(name: Any, where: str, report: CaseReport) -> None:
    if name not in DEMO_PEOPLE:
        report.problems.append(f"{where}: {name!r} is not one of the four fictional demo people")


def check_extraction(payload: dict[str, Any], report: CaseReport) -> None:
    try:
        extraction = ExtractionResult.model_validate(payload)
    except ValidationError as error:
        for issue in error.errors():
            location = ".".join(str(part) for part in issue["loc"]) or "(root)"
            report.problems.append(f"extraction {location}: {issue['msg']}")
        return

    report.extraction = extraction

    # The fixture is also the wire payload the BE stub serves, so it must already be in wire shape.
    if extraction.model_dump(mode="json", by_alias=True) != payload:
        report.problems.append("extraction: file is not identical to its serialized wire form")

    if not extraction.evidence.authority_clause.strip():
        report.problems.append("extraction evidence.authorityClause: empty quote")

    for representative in extraction.representatives:
        where = f"extraction representative {representative.name!r}"
        check_person_name(representative.name, where, report)
        check_masked_id(representative.national_id, where, report)
        for co_signer in representative.co_signers:
            check_person_name(co_signer, f"{where} coSigners", report)

    # Rule coSigners hold representative ids ("rep-2"), not names — the schema's own
    # cross-field validator already rejects an id that resolves to nobody.
    for index, rule in enumerate(extraction.rules or []):
        if not rule.evidence.quote.strip():
            report.problems.append(f"extraction rules[{index}]: empty evidence quote")


def check_expected(payload: dict[str, Any], report: CaseReport) -> None:
    report.expected = payload

    application = payload.get("application", {})
    check_person_name(application.get("applicant_name"), "application applicant_name", report)
    check_masked_id(application.get("applicant_tckn"), "application applicant_tckn", report)

    for mersis, company in payload.get("registry", {}).items():
        for rep in company.get("reps", []):
            where = f"registry {mersis} rep {rep.get('name')!r}"
            check_person_name(rep.get("name"), where, report)
            check_masked_id(rep.get("tckn"), where, report)

    if application.get("mersis") not in payload.get("registry", {}):
        report.problems.append("registry: no entry for the application's mersis number")

    statuses = read_statuses(payload, report)
    if statuses is None:
        return

    try:
        expected_verdict = CheckVerdict(payload["expected_verdict"])
    except (KeyError, ValueError):
        report.problems.append(
            f"expected_verdict: unknown value {payload.get('expected_verdict')!r}"
        )
        return

    derived = verdict_from_statuses(statuses)
    if derived is not expected_verdict:
        report.problems.append(
            f"expected_verdict {expected_verdict} contradicts the statuses, which imply {derived}"
        )


def read_statuses(
    payload: dict[str, Any], report: CaseReport
) -> dict[CheckId, CheckStatus] | None:
    """Returns the nine expected statuses, or None if the list is not the frozen nine in order."""

    entries = payload.get("expected_checks", [])
    try:
        ids = tuple(CheckId(entry["id"]) for entry in entries)
    except (KeyError, TypeError, ValueError):
        report.problems.append("expected_checks: entries must be {id, status} with a known id")
        return None

    if ids != CHECK_IDS:
        missing = [check_id.value for check_id in CHECK_IDS if check_id not in ids]
        detail = f"missing {', '.join(missing)}" if missing else "wrong order"
        report.problems.append(f"expected_checks: must be the nine frozen ids in order — {detail}")
        return None

    statuses: dict[CheckId, CheckStatus] = {}
    for entry in entries:
        try:
            statuses[CheckId(entry["id"])] = CheckStatus(entry["status"])
        except (KeyError, ValueError):
            report.problems.append(f"expected_checks {entry.get('id')}: unknown status")
            return None
    return statuses


def check_report(payload: dict[str, Any], report: CaseReport) -> None:
    """Validates the standalone CheckReport fixture and guards it against drift.

    The file must equal analyze()'s live output for this case's extraction, application, and
    registry — it is a generated snapshot, never a hand-maintained second copy of the truth.
    """

    try:
        parsed = CheckReport.model_validate(payload)
    except ValidationError as error:
        for issue in error.errors():
            location = ".".join(str(part) for part in issue["loc"]) or "(root)"
            report.problems.append(f"report {location}: {issue['msg']}")
        return

    if report.extraction is None or report.expected is None:
        report.problems.append("report: cannot cross-check, extraction or expected fixture is invalid")
        return

    request = AnalyzeRequest.model_validate(
        {
            "extraction": report.extraction.model_dump(mode="json", by_alias=True),
            "application": report.expected.get("application", {}),
            "registry": report.expected.get("registry", {}),
            "as_of": report.expected.get("as_of"),
        }
    )
    live = analyze(request).model_dump(mode="json", by_alias=True)
    if parsed.model_dump(mode="json", by_alias=True) != live:
        report.problems.append(
            "report: file does not match analyze() output — regenerate, never hand-edit"
        )


def check_case(case: int, fixtures_dir: Path = FIXTURES_DIR) -> CaseReport:
    report = CaseReport(case=case)

    extraction_payload = load_json(extraction_path(case, fixtures_dir), report)
    if extraction_payload is not None:
        check_extraction(extraction_payload, report)

    expected_payload = load_json(expected_path(case, fixtures_dir), report)
    if expected_payload is not None:
        check_expected(expected_payload, report)

    report_payload = load_json(report_path(case, fixtures_dir), report)
    if report_payload is not None:
        check_report(report_payload, report)

    return report


def check_shared_document(fixtures_dir: Path = FIXTURES_DIR) -> list[str]:
    """Case 4 must be case 1's document byte for byte — the conflict comes from the registry."""

    first, second = (extraction_path(case, fixtures_dir) for case in SHARED_DOCUMENT_CASES)
    if not (first.exists() and second.exists()):
        return ["case 4: cannot compare with case 1, a fixture file is missing"]
    if first.read_bytes() != second.read_bytes():
        return ["case 4: fixture differs from case 1 — it must be the same document"]
    return []


def format_amount(value_kurus: int | None) -> str:
    """value_kurus is integer kuruş (1 TL = 100 kuruş); displayed here as whole TL."""

    if value_kurus is None:
        return "limitsiz"
    return f"{value_kurus // 100:,}".replace(",", ".") + " TL"


def describe_people(report: CaseReport) -> str:
    extraction = report.extraction
    if extraction is None:
        return "—"
    parts = []
    for representative in extraction.representatives:
        detail = representative.mode.value
        if representative.limits is not None:
            detail += f" ≤ {format_amount(representative.limits)}"
        if representative.co_signers:
            detail += " + " + ", ".join(representative.co_signers)
        parts.append(f"{representative.name} ({detail})")
    return " · ".join(parts)


def off_colour_checks(report: CaseReport) -> list[str]:
    entries = (report.expected or {}).get("expected_checks", [])
    return [
        f"{entry['status']:>5}  {entry['id']}"
        for entry in entries
        if isinstance(entry, dict) and entry.get("status") != "green"
    ]


def print_report(report: CaseReport) -> None:
    expected = report.expected or {}
    extraction = report.extraction

    print(f"case {report.case}  {expected.get('title', '')}")
    print(f"   document    {expected.get('document', '—')}")
    if extraction is not None:
        review = ", ".join(extraction.fields_needing_review) or "—"
        print(
            f"   extraction  {extraction.document_id} · {extraction.company.name}"
            f" · geçerlilik {extraction.valid_until}"
        )
        print(f"   people      {describe_people(report)}")
        print(f"   rules       {len(extraction.rules or [])} · fieldsNeedingReview: {review}")
    print(f"   expected    {expected.get('expected_verdict', '—')}")
    for line in off_colour_checks(report) or ["green  all nine checks"]:
        print(f"               {line}")
    print(f"   result      {'OK' if report.ok else 'FAILED'}")
    for problem in report.problems:
        print(f"     - {problem}")
    print()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the four demo fixtures and print their expected outcomes."
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=FIXTURES_DIR,
        help="directory holding case{n}.json and case{n}.expected.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    fixtures_dir = parse_args(argv).fixtures_dir
    print(f"YetkiCheck — demo fixture check ({fixtures_dir})\n")

    found = discover_cases(fixtures_dir)
    if not found:
        # An empty directory is a clean slate, not a failure: AI-02B may simply not have run yet.
        print("no fixtures found")
        return 0

    reports = [check_case(case, fixtures_dir) for case in CASE_NUMBERS]
    for report in reports:
        print_report(report)

    problems = check_shared_document(fixtures_dir)
    print("case 4 uses case 1's document: " + ("OK" if not problems else "FAILED"))
    for problem in problems:
        print(f"  - {problem}")

    extras = [case for case in found if case not in CASE_NUMBERS]
    if extras:
        problems.append(f"unexpected fixture files for cases {extras}: the demo has exactly four")
        print(f"  - {problems[-1]}")

    failed = sorted({report.case for report in reports if not report.ok})
    print()
    if failed or problems:
        cases = ", ".join(str(case) for case in failed) or "—"
        print(f"FAILED — cases {cases}")
        return 1
    print("ALL FOUR FIXTURES VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
