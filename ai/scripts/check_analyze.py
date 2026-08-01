# ai/scripts/check_analyze.py
"""Runs the nine checks over the demo fixtures and prints every row against its expectation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.compare import analyze  # noqa: E402
from ai.schema import AnalyzeRequest, CheckReport  # noqa: E402
from ai.scripts.check_fixtures import CASE_NUMBERS, expected_path, extraction_path  # noqa: E402

STATUS_WIDTH = 6
TITLE_WIDTH = 24


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_request(case: int) -> AnalyzeRequest:
    expected = load(expected_path(case))
    return AnalyzeRequest.model_validate(
        {
            "extraction": load(extraction_path(case)),
            "application": expected["application"],
            "registry": expected["registry"],
            "as_of": expected["as_of"],
        }
    )


def render_evidence(evidence: dict[str, Any]) -> str:
    pairs = [f"{key}: {value}" for key, value in evidence.items() if value is not None]
    return " · ".join(pairs)


def print_case(case: int, report: CheckReport, expected: dict[str, Any]) -> bool:
    """Prints one case and returns True when it matches its expected fixture exactly."""

    expected_statuses = {entry["id"]: entry["status"] for entry in expected["expected_checks"]}
    verdict_ok = report.verdict.value == expected["expected_verdict"]

    print(f"case {case}  {expected['title']}")
    print(
        f"  verdict   {report.verdict.value:<20}"
        + ("OK" if verdict_ok else f"FAILED, expected {expected['expected_verdict']}")
    )

    rows_ok = True
    for check in report.checks:
        wanted = expected_statuses.get(check.id.value)
        matched = check.status.value == wanted
        rows_ok &= matched
        note = "" if matched else f"   <- expected {wanted}"
        print(
            f"    {check.status.value:<{STATUS_WIDTH}}{check.title:<{TITLE_WIDTH}}"
            f"{check.reason}{note}"
        )
        evidence = render_evidence(check.evidence)
        if evidence:
            print(f"    {'':<{STATUS_WIDTH}}{'':<{TITLE_WIDTH}}{evidence}")
    print()
    return verdict_ok and rows_ok


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run POST /analyze logic over the four demo fixtures."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--case", type=int, choices=CASE_NUMBERS, help="run a single demo case")
    group.add_argument("--all", action="store_true", help="run all four demo cases (default)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    cases = [args.case] if args.case else list(CASE_NUMBERS)

    print("YetkiCheck — deterministic nine-check analysis\n")

    failed = []
    for case in cases:
        report = analyze(build_request(case))
        if not print_case(case, report, load(expected_path(case))):
            failed.append(case)

    if failed:
        print(f"FAILED — cases {', '.join(str(case) for case in failed)} differ from their fixtures")
        return 1
    print(f"ALL EXPECTATIONS MET — {len(cases)} case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
