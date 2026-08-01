# ai/scripts/check_validator.py
"""Prints deterministic provenance flags for a saved rich extraction fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.schema import CircularExtraction  # noqa: E402
from ai.validator import validate_extraction  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run annotation-only provenance checks on a rich extraction."
    )
    parser.add_argument("extraction_fixture", type=Path, help="CircularExtraction JSON file")
    parser.add_argument("--summary", action="store_true", help="omit individual flag details")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    print("YetkiCheck — provenance validator\n")
    try:
        payload = json.loads(args.extraction_fixture.resolve().read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "extraction" in payload:
            payload = payload["extraction"]
        extraction = CircularExtraction.model_validate(payload)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"FAILED      {error}")
        return 1

    outcome = validate_extraction(extraction)
    if args.summary:
        counts: dict[str, int] = {}
        for flag in outcome.flags:
            counts[flag.severity.value] = counts.get(flag.severity.value, 0) + 1
        print(f"flags       {len(outcome.flags)} {counts}")
        print(f"review      {len(outcome.fields_needing_review)} fields")
        print(f"anomalies   {len(outcome.anomaly_codes)} codes")
    elif not outcome.flags:
        print("No provenance flags.\n")
    else:
        print(f"  {'severity':<9} {'check':<31} {'page':<6} field")
        for flag in outcome.flags:
            page = str(flag.evidence_page) if flag.evidence_page else "-"
            print(
                f"  {flag.severity.value:<9} {flag.check_name:<31} "
                f"{page:<6} {flag.field_path}"
            )
            print(f"            {flag.anomaly_code}: {flag.message}")
    if not args.summary:
        print("\nfieldsNeedingReview")
        for field in outcome.fields_needing_review:
            print(f"  {field}")
        print("\nanomalyCodes")
        for code in outcome.anomaly_codes:
            print(f"  {code}")
    print("\nOK — annotations only; extraction was not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
