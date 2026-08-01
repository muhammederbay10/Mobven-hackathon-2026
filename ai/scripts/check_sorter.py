# ai/scripts/check_sorter.py
"""Classifies a document's pages and prints the page map for manual stage approval.

Without --live: replays a response recorded by a previous --live run (no network, no cost,
safe for repeated offline use). With --live: makes one real vision-model call — the only place
in this ticket where that is allowed — and records the raw response so this and future offline
runs can replay it. See ai/tests/test_sorter.py's module docstring for why hand-written stand-ins,
not this recording mechanism, currently back the offline pytest suite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.render import PageImages, RenderError, render_path  # noqa: E402
from ai.schema import PageClassification  # noqa: E402
from ai.sorter import SUPPORTING_ONLY_LABELS, SorterOutcome, classify_pages  # noqa: E402

# Recordings are real model output once captured; they hold no document bytes and no personal
# data, only the JSON the model returned, so they may be committed and replayed offline.
RECORDINGS_DIR = REPO_ROOT / "ai" / "tests" / "fixtures" / "sorter_recordings"


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recording_path(digest: str) -> Path:
    return RECORDINGS_DIR / f"{digest}.json"


def replay_caller(raw_responses: list[str]):
    queue = list(raw_responses)

    def call(system_prompt: str, user_content: list[dict]) -> str:
        if not queue:
            raise RuntimeError("recording exhausted: it has fewer responses than attempts made")
        return queue.pop(0)

    return call


def describe_labels(page: PageClassification) -> str:
    names = ", ".join(label.value for label in page.labels)
    if all(label in SUPPORTING_ONLY_LABELS for label in page.labels):
        return f"{names}  [supporting-only]"
    return names


def print_page_map(source: Path, outcome: SorterOutcome) -> None:
    page_map = outcome.page_map
    print(f"file        {source}")
    print(f"attempts    {outcome.attempts}")
    print(f"degraded    {outcome.degraded}")
    if page_map.company_name_line:
        print(f"company     {page_map.company_name_line}")
    for hint in page_map.structure_hints:
        print(f"hint        {hint}")
    print()
    print(f"  {'page':>4}  {'continues':<11}labels")
    for page in page_map.pages:
        marker = "-> next" if page.continues_on_next else ""
        print(f"  {page.page:>4}  {marker:<11}{describe_labels(page)}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify a document's pages with the Sorter.")
    parser.add_argument("path", type=Path, help="PDF, JPG, JPEG, or PNG to classify")
    parser.add_argument(
        "--live",
        action="store_true",
        help="call the configured vision model and record the response (costs money, needs a key)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    path = args.path
    print("YetkiCheck — page sorter\n")

    try:
        pages: list[PageImages] = render_path(path)
    except RenderError as error:
        print(f"FAILED      could not render {path}: {error}")
        return 1

    digest = digest_of(path)
    record = recording_path(digest)

    if args.live:
        outcome = classify_pages(pages)
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        record.write_text(
            json.dumps({"source_sha256": digest, "raw_responses": list(outcome.raw_responses)}, indent=2),
            encoding="utf-8",
        )
        try:
            shown = record.relative_to(REPO_ROOT)
        except ValueError:
            shown = record
        print(f"recorded    {shown}\n")
    else:
        if not record.exists():
            print(
                f"no recorded response for {path.name} (sha256 {digest[:12]}...).\n"
                f"Run with --live once to call the model and record one: "
                f"python ai/scripts/check_sorter.py {path} --live"
            )
            return 1
        recorded = json.loads(record.read_text(encoding="utf-8"))
        outcome = classify_pages(pages, call_model=replay_caller(recorded["raw_responses"]))

    print_page_map(path, outcome)
    print()
    if outcome.degraded:
        print("DEGRADED — the sorter could not produce a valid page map; every page is under review")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
