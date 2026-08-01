# ai/sorter.py
"""Classifies page images into the closed twelve-label taxonomy. Reads labels only, never content."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

if __package__:
    from .prompts.sorter import RETRY_TEMPLATE, SYSTEM_PROMPT, USER_INSTRUCTION
    from .render import PageImages
    from .schema import PageClassification, PageLabel, PageMap
else:  # uvicorn main:app started from inside ai/
    from prompts.sorter import RETRY_TEMPLATE, SYSTEM_PROMPT, USER_INSTRUCTION
    from render import PageImages
    from schema import PageClassification, PageLabel, PageMap

MAX_ATTEMPTS = 2

# Annex sections and imza_beyannamesi confirm but never create authority (AI_BACKEND_PLAN §6.2);
# a page carrying only these labels has nothing for the chunker to extract rules from directly.
ANNEX_LABELS = frozenset(
    {PageLabel.IC_YONERGE_ANNEX, PageLabel.BOARD_RESOLUTION_ANNEX, PageLabel.GAZETTE_ANNEX}
)
SUPPORTING_ONLY_LABELS = ANNEX_LABELS | {PageLabel.IMZA_BEYANNAMESI}
UTILITY_LABELS = frozenset({PageLabel.COVER_OR_BLANK, PageLabel.OTHER_UNKNOWN})

# What the Sorter emits when both attempts fail: every page visible, nothing invented, nothing
# lost. The chunker treats other_unknown as "send to a human", never as "silently drop".
DEGRADED_HINT_PREFIX = "sorter degraded: "

ModelCaller = Callable[[str, list[dict[str, Any]]], str]


class SorterError(Exception):
    """Raised only when there is nothing to classify — every other failure degrades instead."""


class _InvalidPageMap(ValueError):
    """Internal: the parsed JSON validated but didn't cover every shown page exactly once."""


@dataclass(frozen=True)
class SorterOutcome:
    """What classify_pages returns: the page map, whether it is a degraded fallback, and why."""

    page_map: PageMap
    degraded: bool
    attempts: int
    raw_responses: tuple[str, ...]


def is_supporting_only(page: PageClassification) -> bool:
    """True if every label on this page is annex or imza_beyannamesi — never a primary section."""

    return all(label in SUPPORTING_ONLY_LABELS for label in page.labels)


def classify_pages(
    pages: Sequence[PageImages],
    *,
    call_model: ModelCaller | None = None,
    model: str | None = None,
) -> SorterOutcome:
    """Sends every page at sorter resolution in one call; validates; retries once; else degrades.

    A malformed or incomplete response never raises past this function — the pipeline must keep
    moving. The one call_model injection point is what lets tests and diagnostics replay recorded
    text instead of touching the network.
    """

    if not pages:
        raise SorterError("no pages to classify")

    caller = call_model or _default_caller(model)
    content = _build_user_content(pages)
    expected = len(pages)

    raw_responses: list[str] = []
    error_note = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = content if attempt == 1 else content + [_retry_block(error_note)]
        raw = caller(SYSTEM_PROMPT, prompt)
        raw_responses.append(raw)
        try:
            page_map = _parse(raw, expected_pages=expected)
        except (json.JSONDecodeError, ValidationError, _InvalidPageMap) as error:
            error_note = str(error)
            continue
        return SorterOutcome(
            page_map=page_map, degraded=False, attempts=attempt, raw_responses=tuple(raw_responses)
        )

    return SorterOutcome(
        page_map=_degraded_page_map(expected, error_note),
        degraded=True,
        attempts=MAX_ATTEMPTS,
        raw_responses=tuple(raw_responses),
    )


def _default_caller(model: str | None) -> ModelCaller:
    from openai import OpenAI  # deferred: keeps offline tests from requiring an API key at import

    resolved_model = model or os.getenv("EXTRACTION_MODEL")
    if not resolved_model:
        raise SorterError("EXTRACTION_MODEL is not set in ai/.env")
    client = OpenAI()

    def call(system_prompt: str, user_content: list[dict[str, Any]]) -> str:
        response = client.chat.completions.create(
            model=resolved_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return response.choices[0].message.content or ""

    return call


def _build_user_content(pages: Sequence[PageImages]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": USER_INSTRUCTION.format(page_count=len(pages))}
    ]
    for page in pages:
        content.append({"type": "text", "text": f"Page {page.page_no}:"})
        content.append({"type": "image_url", "image_url": {"url": _data_url(page.sort_png)}})
    return content


def _data_url(png_bytes: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"


def _retry_block(error: str) -> dict[str, Any]:
    return {"type": "text", "text": RETRY_TEMPLATE.format(error=error or "unknown error")}


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if stripped.endswith("```"):
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def _parse(raw: str, expected_pages: int) -> PageMap:
    payload = json.loads(_strip_code_fence(raw))
    page_map = PageMap.model_validate(payload)

    seen = {page.page for page in page_map.pages}
    wanted = set(range(1, expected_pages + 1))
    if seen != wanted:
        missing = sorted(wanted - seen)
        extra = sorted(seen - wanted)
        raise _InvalidPageMap(
            f"page map covers {sorted(seen)}, expected {sorted(wanted)} "
            f"(missing={missing}, extra={extra})"
        )
    return page_map


def _degraded_page_map(page_count: int, reason: str) -> PageMap:
    hint = DEGRADED_HINT_PREFIX + (reason or "no reason recorded")
    return PageMap(
        structure_hints=[hint],
        pages=[
            PageClassification(page=number, labels=[PageLabel.OTHER_UNKNOWN])
            for number in range(1, page_count + 1)
        ],
    )
