# ai/scripts/check_normalizer.py
"""Normalizes a saved raw-chunk recording and prints the rich extraction offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.normalizer import NormalizerConfigurationError, normalize_extraction  # noqa: E402
from ai.schema import ChunkExtractionResult, PageMap  # noqa: E402
from ai.scripts.check_sorter import recording_path as sorter_recording_path  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge a raw extractor recording without any model calls."
    )
    parser.add_argument("raw_chunks_fixture", type=Path, help="JSON extractor recording")
    parser.add_argument("--summary", action="store_true", help="omit the full extraction JSON")
    parser.add_argument("--output", type=Path, help="optionally save CircularExtraction JSON")
    return parser.parse_args(argv)


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _load_page_map(payload: dict) -> PageMap:
    if "page_map" in payload:
        return PageMap.model_validate(payload["page_map"])
    digest = payload.get("source_sha256")
    if not digest:
        raise ValueError("fixture requires page_map or source_sha256")
    path = sorter_recording_path(digest)
    if not path.exists():
        raise FileNotFoundError(f"sorter recording not found: {path}")
    sorter_record = json.loads(path.read_text(encoding="utf-8"))
    raw_responses = sorter_record.get("raw_responses", [])
    if not raw_responses:
        raise ValueError("sorter recording contains no response")
    return PageMap.model_validate(json.loads(_strip_code_fence(raw_responses[-1])))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    print("YetkiCheck — extraction normalizer\n")
    try:
        path = args.raw_chunks_fixture.resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("fixture must be an object with results and page_map/source_sha256")
        raw_results = payload.get("results", [])
        page_map = _load_page_map(payload)
        results = [ChunkExtractionResult.model_validate(item) for item in raw_results]
        document_id = payload.get("document_id") or payload.get("source_sha256", path.stem)[:16]
        extraction = normalize_extraction(document_id, page_map, results)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        ValidationError,
        NormalizerConfigurationError,
    ) as error:
        print(f"FAILED      {error}")
        return 1

    print(f"document    {extraction.document_id}")
    print(f"company     {extraction.company.legal_name}")
    print(f"signatories {len(extraction.signatories)}")
    print(f"rules       {len(extraction.rules)}")
    print(f"references  {len(extraction.references)}")
    print(f"raw chunks  {len(extraction.raw_chunks)}\n")
    rendered = json.dumps(extraction.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"saved       {output_path}")
    if not args.summary:
        print(rendered)
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
