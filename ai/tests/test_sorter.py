# ai/tests/test_sorter.py
"""Offline sorter tests.

The JSON strings below are hand-authored stand-ins for a vision model's response, not recordings
of a real API call — this environment has no OPENAI_API_KEY. They exist to test classify_pages'
own logic (parsing, retry, degrade, page-content shape) without ever touching the network, per the
project rule that pytest must never call OpenAI. When a real key is available, run
`ai/scripts/check_sorter.py <path> --live` against a real document to capture an actual recording;
that recording is what should back any future "recorded real response" fixture, not these.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from ai.render import PageImages
from ai.schema import PageLabel
from ai.sorter import (
    ANNEX_LABELS,
    SUPPORTING_ONLY_LABELS,
    SorterError,
    _default_caller,
    classify_pages,
    is_supporting_only,
)

# classify_pages never looks past .page_no and .sort_png, so a blank 1x1 PNG stands in for a page.
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\nIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def page(number: int) -> PageImages:
    return PageImages(
        page_no=number, sort_png=_BLANK_PNG, extract_png=_BLANK_PNG, sort_size=(1, 1), extract_size=(1, 1)
    )


def scripted_caller(*responses: str):
    """A call_model stand-in that returns one scripted response per call, in order."""

    queue = list(responses)
    calls: list[tuple[str, list[dict]]] = []

    def call(system_prompt: str, user_content: list[dict]) -> str:
        calls.append((system_prompt, user_content))
        return queue.pop(0)

    call.calls = calls  # type: ignore[attr-defined]
    return call


# Hand-authored stand-in for a two-page synthetic circular (case1-shaped): everything the demo
# needs sits on page 1, specimens and the notary block sit on page 2.
TWO_PAGE_RESPONSE = json.dumps(
    {
        "company_name_line": "ABC TEKNOLOJİ LİMİTED ŞİRKETİ",
        "structure_hints": ["one signatory signs alone up to a threshold, two above it"],
        "pages": [
            {
                "page": 1,
                "labels": ["identity_header", "dayanak", "appointments", "rules"],
                "continues_on_next": False,
            },
            {"page": 2, "labels": ["specimens", "notary_block"], "continues_on_next": False},
        ],
    }
)

# Hand-authored stand-in mirroring the nine-page structure AI_BACKEND_PLAN section 6.3 uses as its
# own worked example (appointments 1-2, rules 3-5, specimens 6-8, a gazette annex on 9).
NINE_PAGE_RESPONSE = json.dumps(
    {
        "company_name_line": "YILDIZ TEKSTİL SANAYİ VE TİCARET LİMİTED ŞİRKETİ",
        "structure_hints": ["groups A and B exist"],
        "pages": [
            {"page": 1, "labels": ["identity_header", "appointments"], "continues_on_next": True},
            {"page": 2, "labels": ["appointments"], "continues_on_next": False},
            {"page": 3, "labels": ["dayanak", "rules"], "continues_on_next": True},
            {"page": 4, "labels": ["rules"], "continues_on_next": True},
            {"page": 5, "labels": ["rules", "notary_block"], "continues_on_next": False},
            {"page": 6, "labels": ["specimens"], "continues_on_next": False},
            {"page": 7, "labels": ["specimens"], "continues_on_next": False},
            {"page": 8, "labels": ["specimens"], "continues_on_next": False},
            {"page": 9, "labels": ["gazette_annex"], "continues_on_next": False},
        ],
    }
)


def test_a_short_circular_puts_several_primary_labels_on_one_page() -> None:
    outcome = classify_pages([page(1), page(2)], call_model=scripted_caller(TWO_PAGE_RESPONSE))

    assert not outcome.degraded
    first = outcome.page_map.pages[0]
    assert set(first.labels) == {
        PageLabel.IDENTITY_HEADER,
        PageLabel.DAYANAK,
        PageLabel.APPOINTMENTS,
        PageLabel.RULES,
    }
    assert outcome.page_map.company_name_line == "ABC TEKNOLOJİ LİMİTED ŞİRKETİ"


def test_nine_page_structure_spans_match_the_documented_example() -> None:
    outcome = classify_pages([page(n) for n in range(1, 10)], call_model=scripted_caller(NINE_PAGE_RESPONSE))

    by_page = {p.page: set(p.labels) for p in outcome.page_map.pages}
    assert by_page[1] == {PageLabel.IDENTITY_HEADER, PageLabel.APPOINTMENTS}
    assert by_page[2] == {PageLabel.APPOINTMENTS}
    assert all(PageLabel.RULES in by_page[n] for n in (3, 4, 5))
    assert all(by_page[n] == {PageLabel.SPECIMENS} for n in (6, 7, 8))
    assert by_page[9] == {PageLabel.GAZETTE_ANNEX}


def test_appointments_continuation_is_flagged_across_the_page_break() -> None:
    outcome = classify_pages([page(n) for n in range(1, 10)], call_model=scripted_caller(NINE_PAGE_RESPONSE))

    first = next(p for p in outcome.page_map.pages if p.page == 1)
    assert first.continues_on_next


def test_gazette_annex_page_is_supporting_only() -> None:
    outcome = classify_pages([page(n) for n in range(1, 10)], call_model=scripted_caller(NINE_PAGE_RESPONSE))

    annex_page = next(p for p in outcome.page_map.pages if p.page == 9)
    assert is_supporting_only(annex_page)
    assert set(annex_page.labels) <= ANNEX_LABELS


def test_a_mixed_primary_and_annex_page_is_not_supporting_only() -> None:
    # A short document can fold a small annex note onto its rules page — the mix must stay visible.
    response = json.dumps({"pages": [{"page": 1, "labels": ["rules", "gazette_annex"]}]})

    outcome = classify_pages([page(1)], call_model=scripted_caller(response))

    assert not is_supporting_only(outcome.page_map.pages[0])


def test_imza_beyannamesi_alone_is_supporting_only_never_a_circular() -> None:
    response = json.dumps({"pages": [{"page": 1, "labels": ["imza_beyannamesi"]}]})
    outcome = classify_pages([page(1)], call_model=scripted_caller(response))

    assert is_supporting_only(outcome.page_map.pages[0])
    assert PageLabel.IMZA_BEYANNAMESI in SUPPORTING_ONLY_LABELS


def test_malformed_json_triggers_one_retry_then_succeeds() -> None:
    caller = scripted_caller("not json at all", TWO_PAGE_RESPONSE)

    outcome = classify_pages([page(1), page(2)], call_model=caller)

    assert outcome.attempts == 2
    assert not outcome.degraded
    # The retry message must carry the parser's own error so the model can act on it.
    retry_text = caller.calls[1][1][-1]["text"]
    assert "geçersiz" in retry_text.lower()


def test_an_invalid_label_triggers_one_retry_then_succeeds() -> None:
    bad = json.dumps({"pages": [{"page": 1, "labels": ["not_a_real_label"]}]})
    caller = scripted_caller(bad, TWO_PAGE_RESPONSE)

    outcome = classify_pages([page(1), page(2)], call_model=caller)

    assert outcome.attempts == 2
    assert not outcome.degraded


def test_a_missing_page_triggers_one_retry_then_succeeds() -> None:
    incomplete = json.dumps({"pages": [{"page": 1, "labels": ["identity_header"]}]})
    caller = scripted_caller(incomplete, TWO_PAGE_RESPONSE)

    outcome = classify_pages([page(1), page(2)], call_model=caller)

    assert outcome.attempts == 2
    assert not outcome.degraded


def test_two_malformed_responses_degrade_instead_of_raising() -> None:
    outcome = classify_pages([page(1), page(2)], call_model=scripted_caller("nope", "still nope"))

    assert outcome.degraded
    assert outcome.attempts == 2
    assert [p.page for p in outcome.page_map.pages] == [1, 2]
    assert all(p.labels == [PageLabel.OTHER_UNKNOWN] for p in outcome.page_map.pages)
    assert outcome.page_map.structure_hints[0].startswith("sorter degraded: ")


def test_a_degraded_page_map_still_validates_and_keeps_every_page_visible() -> None:
    outcome = classify_pages([page(n) for n in range(1, 5)], call_model=scripted_caller("x", "y"))

    assert [p.page for p in outcome.page_map.pages] == [1, 2, 3, 4]


def test_no_pages_raises_instead_of_calling_the_model() -> None:
    with pytest.raises(SorterError, match="no pages"):
        classify_pages([], call_model=scripted_caller(TWO_PAGE_RESPONSE))


def test_markdown_code_fences_around_the_json_are_stripped() -> None:
    fenced = f"```json\n{TWO_PAGE_RESPONSE}\n```"

    outcome = classify_pages([page(1), page(2)], call_model=scripted_caller(fenced))

    assert not outcome.degraded


def test_every_shown_page_is_sent_as_a_labelled_image_in_order() -> None:
    caller = scripted_caller(TWO_PAGE_RESPONSE)

    classify_pages([page(1), page(2)], call_model=caller)

    _, content = caller.calls[0]
    texts = [block["text"] for block in content if block["type"] == "text"]
    images = [block for block in content if block["type"] == "image_url"]
    assert texts[1:] == ["Page 1:", "Page 2:"]  # texts[0] is the instruction preamble
    assert len(images) == 2
    assert images[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_default_caller_requires_extraction_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTRACTION_MODEL", raising=False)

    with pytest.raises(SorterError, match="EXTRACTION_MODEL"):
        classify_pages([page(1)])


def test_default_caller_omits_unsupported_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            request.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    fake_openai = SimpleNamespace(OpenAI=lambda: fake_client)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("EXTRACTION_MODEL", "test-model")

    caller = _default_caller(None)
    caller("system", [{"type": "text", "text": "classify"}])

    assert request["model"] == "test-model"
    assert request["response_format"] == {"type": "json_object"}
    assert "temperature" not in request
