# ai/scripts/check_extractors.py
"""Runs sorter, chunker, and section extractors with live recording or offline replay."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.chunker import Chunk, ChunkerError, build_chunks  # noqa: E402
from ai.extractors import ExtractorConfigurationError, extract_chunks  # noqa: E402
from ai.render import RenderError, render_path  # noqa: E402
from ai.schema import (  # noqa: E402
    ChunkExtractionResult,
    ExtractorProgress,
    ExtractorRole,
    ExtractorStatus,
)
from ai.scripts.check_sorter import (  # noqa: E402
    RECORDINGS_DIR as SORTER_RECORDINGS_DIR,
)
from ai.scripts.check_sorter import digest_of, recording_path, replay_caller  # noqa: E402
from ai.sorter import classify_pages  # noqa: E402


# Raw extraction can contain personal data, so live recordings stay in the gitignored runtime cache.
EXTRACTOR_RECORDINGS_DIR = REPO_ROOT / "ai" / "cache" / "extractor_recordings"


def extractor_recording_path(digest: str) -> Path:
    return EXTRACTOR_RECORDINGS_DIR / f"{digest}.json"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect section extraction output for one PDF or image."
    )
    parser.add_argument("path", type=Path, help="PDF, JPG, JPEG, or PNG to inspect")
    parser.add_argument(
        "--live",
        action="store_true",
        help="call configured vision models and save a private cache recording",
    )
    parser.add_argument(
        "--no-witness",
        action="store_true",
        help="disable the optional rules-only witness pass",
    )
    return parser.parse_args(argv)


def _load_sorter_record(digest: str) -> dict:
    path = recording_path(digest)
    if not path.exists():
        raise FileNotFoundError(
            "no sorter recording exists; run this command with --live once first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _save_sorter_record(digest: str, raw_responses: tuple[str, ...]) -> None:
    SORTER_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    recording_path(digest).write_text(
        json.dumps(
            {"source_sha256": digest, "raw_responses": list(raw_responses)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _save_extractor_record(
    digest: str, source: Path, results: list[ChunkExtractionResult]
) -> Path:
    path = extractor_recording_path(digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source_sha256": digest,
                "source_name": source.name,
                "results": [result.model_dump(mode="json") for result in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def replay_extractor_caller(recorded_results: list[dict]):
    responses: dict[tuple[str, str], deque[str]] = defaultdict(deque)
    for item in recorded_results:
        key = (item["chunk_id"], item["role"])
        responses[key].extend(item.get("raw_responses", []))

    async def call(chunk, role, model, system_prompt, user_content) -> str:
        key = (chunk.chunk_id, role.value)
        if not responses[key]:
            raise RuntimeError(f"extractor recording exhausted for {key[0]} ({key[1]})")
        return responses[key].popleft()

    return call


def print_progress(event: ExtractorProgress) -> None:
    print(
        f"[{event.state.value:7}] {event.chunk_id:<24} "
        f"{event.role.value:<7} {event.detail}"
    )


def print_results(chunks: list[Chunk], results: list[ChunkExtractionResult]) -> None:
    print("\nchunks")
    for item in chunks:
        pages = ",".join(str(page) for page in item.pages)
        marker = " supporting-only" if item.supporting_only else ""
        print(f"  {item.chunk_id:<24} {item.agent:<12} pages={pages}{marker}")

    print("\noutputs")
    for result in results:
        print(
            f"\n--- {result.chunk_id} / {result.role.value} / "
            f"{result.status.value} / attempts={result.attempts} ---"
        )
        if result.output is not None:
            print(
                json.dumps(
                    result.output.model_dump(mode="json"), ensure_ascii=False, indent=2
                )
            )
        elif result.error:
            print(result.error)


def _recorded_model(recorded_results: list[dict], role: ExtractorRole) -> str:
    for item in recorded_results:
        if item.get("role") == role.value and item.get("model"):
            return item["model"]
    return "recorded-response"


def _recorded_witness_model(recorded_results: list[dict], disabled: bool) -> str:
    if disabled:
        return ""
    if any(item.get("role") == ExtractorRole.WITNESS.value for item in recorded_results):
        return _recorded_model(recorded_results, ExtractorRole.WITNESS)
    return ""


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(REPO_ROOT / "ai" / ".env")
    args = parse_args(argv)
    source = args.path.resolve()
    print("YetkiCheck — section extractors\n")

    try:
        pages = render_path(source)
        digest = digest_of(source)
        if args.live:
            sorter_outcome = classify_pages(pages)
            _save_sorter_record(digest, sorter_outcome.raw_responses)
        else:
            sorter_record = _load_sorter_record(digest)
            sorter_outcome = classify_pages(
                pages, call_model=replay_caller(sorter_record["raw_responses"])
            )
        chunks = build_chunks(sorter_outcome.page_map, pages)
    except (FileNotFoundError, RenderError, ChunkerError) as error:
        print(f"FAILED      {error}")
        return 1

    try:
        if args.live:
            witness_model = "" if args.no_witness else None
            results = asyncio.run(
                extract_chunks(chunks, witness_model=witness_model, progress=print_progress)
            )
            saved = _save_extractor_record(digest, source, results)
            print(f"\nrecorded    {saved.relative_to(REPO_ROOT)}")
        else:
            record_path = extractor_recording_path(digest)
            if not record_path.exists():
                print(
                    "FAILED      no private extractor recording exists; "
                    "run this command with --live once first"
                )
                return 1
            recorded = json.loads(record_path.read_text(encoding="utf-8"))
            recorded_results = recorded["results"]
            results = asyncio.run(
                extract_chunks(
                    chunks,
                    call_model=replay_extractor_caller(recorded_results),
                    extraction_model=_recorded_model(
                        recorded_results, ExtractorRole.PRIMARY
                    ),
                    witness_model=_recorded_witness_model(
                        recorded_results, disabled=args.no_witness
                    ),
                    progress=print_progress,
                )
            )
    except (ExtractorConfigurationError, RuntimeError) as error:
        print(f"FAILED      {error}")
        return 1

    print_results(chunks, results)
    failures = [result for result in results if result.status is ExtractorStatus.FAILED]
    print()
    if sorter_outcome.degraded or failures:
        print(
            f"DEGRADED — sorter_degraded={sorter_outcome.degraded}, "
            f"chunk_failures={len(failures)}"
        )
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
