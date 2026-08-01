# ai/scripts/check_pipeline.py
"""Runs one document through the complete extraction pipeline in live, stub, or replay mode."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.extract import extract_document  # noqa: E402
from ai.schema import FlagSeverity, PipelineMode  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full YetkiCheck extraction pipeline.")
    parser.add_argument("path", type=Path, help="PDF, JPEG, or PNG document")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in PipelineMode],
        default=None,
        help="override AI_MODE from ai/.env",
    )
    parser.add_argument("--document-id", help="response document ID; defaults to filename stem")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore and do not write live cache entries",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    path = args.path.resolve()
    data = path.read_bytes()
    outcome = await extract_document(
        data,
        path.name,
        args.document_id or path.stem,
        mode=args.mode,
        cache_enabled=False if args.no_cache else None,
    )
    result = outcome.result
    severity = Counter(
        flag.severity for flag in outcome.circular.provenance_flags
    ) if outcome.circular else Counter()

    print("YetkiCheck — complete extraction pipeline\n")
    print(f"file          {path.name}")
    print(f"mode          {outcome.mode.value}")
    print(f"sha256        {outcome.source_sha256}")
    print(f"cache hit     {outcome.cache_hit}")
    print(f"degraded      {outcome.degraded}")
    print(f"pages         {outcome.page_count}")
    print(f"chunks        {outcome.chunk_count}")
    print(f"people        {len(result.representatives)}")
    print(f"rules         {len(result.rules or [])}")
    print(f"review fields {len(result.fields_needing_review)}")
    print(
        "flags         "
        f"serious={severity[FlagSeverity.SERIOUS]} "
        f"warn={severity[FlagSeverity.WARN]} "
        f"info={severity[FlagSeverity.INFO]}"
    )
    print("\nstage timings")
    for timing in outcome.timings:
        detail = f"  {timing.detail}" if timing.detail else ""
        print(
            f"  {timing.stage:<10} {timing.seconds:>8.3f}s "
            f"{timing.status.value}{detail}"
        )
    print("\nOK" if not outcome.degraded else "\nDEGRADED — review the reported fields")
    return 1 if outcome.degraded else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(REPO_ROOT / "ai" / ".env")
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
