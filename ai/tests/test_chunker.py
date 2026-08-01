# ai/tests/test_chunker.py
"""Covers deterministic section chunking, overlap, continuation, and uncertainty handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.chunker import ChunkerError, build_chunks
from ai.render import PageImages
from ai.schema import PageMap
from ai.scripts import check_chunker

FIXTURES = Path(__file__).parent / "fixtures" / "page_maps"


def rendered_page(number: int) -> PageImages:
    return PageImages(
        page_no=number,
        sort_png=f"sort-{number}".encode(),
        extract_png=f"extract-{number}".encode(),
        sort_size=(1, 1),
        extract_size=(2, 2),
    )


def pages(count: int) -> list[PageImages]:
    return [rendered_page(number) for number in range(1, count + 1)]


def page_map(payload: dict) -> PageMap:
    return PageMap.model_validate(payload)


def test_nine_page_map_produces_the_documented_seven_chunks() -> None:
    source = FIXTURES / "nine_page.json"
    mapped = PageMap.model_validate_json(source.read_text(encoding="utf-8"))

    chunks = build_chunks(mapped, pages(9))

    assert [(chunk.agent, chunk.pages) for chunk in chunks] == [
        ("appointments", [1, 2]),
        ("rules", [3, 4]),
        ("rules", [4, 5]),
        ("specimens", [6]),
        ("specimens", [7]),
        ("specimens", [8]),
        ("annex", [9]),
    ]
    assert [chunk.chunk_id for chunk in chunks] == [
        "appointments_p1-2",
        "rules_p3-4",
        "rules_p4-5",
        "specimens_p6",
        "specimens_p7",
        "specimens_p8",
        "annex_p9",
    ]
    assert [chunk.supporting_only for chunk in chunks] == [False] * 6 + [True]


def test_rule_windows_overlap_by_exactly_one_page() -> None:
    mapped = page_map(
        {
            "pages": [
                {"page": number, "labels": ["rules"]}
                for number in range(1, 5)
            ]
        }
    )

    chunks = build_chunks(mapped, pages(4))

    assert [chunk.pages for chunk in chunks] == [[1, 2], [2, 3], [3, 4]]
    assert all(
        len(set(left.pages) & set(right.pages)) == 1
        for left, right in zip(chunks, chunks[1:])
    )


def test_appointments_stay_together_and_carry_small_identity_sections() -> None:
    mapped = page_map(
        {
            "pages": [
                {"page": 1, "labels": ["identity_header", "appointments"]},
                {"page": 2, "labels": ["appointments"]},
                {"page": 3, "labels": ["dayanak"]},
                {"page": 4, "labels": ["notary_block"]},
            ]
        }
    )

    chunks = build_chunks(mapped, pages(4))

    assert len(chunks) == 1
    assert chunks[0].agent == "appointments"
    assert chunks[0].pages == [1, 2, 3, 4]
    assert chunks[0].images == [b"extract-1", b"extract-2", b"extract-3", b"extract-4"]


def test_single_page_short_form_is_sent_to_each_relevant_extractor() -> None:
    mapped = page_map(
        {
            "company_name_line": "ABC TEKNOLOJİ LİMİTED ŞİRKETİ",
            "structure_hints": ["A ve B grupları mevcut"],
            "pages": [
                {
                    "page": 1,
                    "labels": [
                        "identity_header",
                        "dayanak",
                        "appointments",
                        "rules",
                        "specimens",
                        "notary_block",
                    ],
                }
            ],
        }
    )

    chunks = build_chunks(mapped, pages(1))

    assert [(chunk.agent, chunk.pages) for chunk in chunks] == [
        ("appointments", [1]),
        ("rules", [1]),
        ("specimens", [1]),
    ]
    assert all("ABC TEKNOLOJİ" in chunk.context_header for chunk in chunks)
    assert all("Page numbers below are absolute." in chunk.context_header for chunk in chunks)


def test_page_level_continuation_does_not_guess_the_next_pages_section() -> None:
    mapped = page_map(
        {
            "pages": [
                {"page": 1, "labels": ["rules"], "continues_on_next": True},
                {"page": 2, "labels": ["other_unknown"]},
            ]
        }
    )

    chunks = build_chunks(mapped, pages(2))

    assert [(chunk.agent, chunk.pages) for chunk in chunks] == [
        ("rules", [1]),
        ("review", [2]),
    ]


def test_mixed_page_continuation_does_not_expand_appointments_or_bridge_rules() -> None:
    mapped = page_map(
        {
            "pages": [
                {
                    "page": 1,
                    "labels": ["identity_header", "appointments", "rules"],
                    "continues_on_next": True,
                },
                {
                    "page": 2,
                    "labels": ["appointments", "ic_yonerge_annex"],
                    "continues_on_next": True,
                },
                {
                    "page": 3,
                    "labels": ["ic_yonerge_annex", "rules"],
                    "continues_on_next": True,
                },
                {
                    "page": 4,
                    "labels": ["ic_yonerge_annex", "rules"],
                    "continues_on_next": True,
                },
                {
                    "page": 5,
                    "labels": ["ic_yonerge_annex", "rules"],
                    "continues_on_next": False,
                },
            ]
        }
    )

    chunks = build_chunks(mapped, pages(5))

    assert [(chunk.agent, chunk.pages) for chunk in chunks] == [
        ("appointments", [1, 2]),
        ("rules", [1]),
        ("rules", [3, 4]),
        ("rules", [4, 5]),
        ("annex", [2, 3, 4, 5]),
    ]


def test_unknown_pages_go_to_review_and_blank_only_pages_are_skipped() -> None:
    mapped = page_map(
        {
            "pages": [
                {"page": 1, "labels": ["cover_or_blank"]},
                {"page": 2, "labels": ["other_unknown"]},
                {"page": 3, "labels": ["cover_or_blank", "rules"]},
            ]
        }
    )

    chunks = build_chunks(mapped, pages(3))

    assert [(chunk.agent, chunk.pages) for chunk in chunks] == [
        ("rules", [3]),
        ("review", [2]),
    ]
    review = chunks[-1]
    assert review.supporting_only
    assert "unclassified section" in review.context_header


def test_annex_is_isolated_even_when_the_page_also_has_primary_rules() -> None:
    mapped = page_map(
        {"pages": [{"page": 1, "labels": ["rules", "gazette_annex"]}]}
    )

    chunks = build_chunks(mapped, pages(1))

    assert [(chunk.agent, chunk.pages, chunk.supporting_only) for chunk in chunks] == [
        ("rules", [1], False),
        ("annex", [1], True),
    ]


def test_different_annex_sections_get_separate_supporting_chunks() -> None:
    mapped = page_map(
        {
            "pages": [
                {"page": 1, "labels": ["ic_yonerge_annex"]},
                {"page": 2, "labels": ["board_resolution_annex"]},
                {"page": 3, "labels": ["cover_or_blank"]},
                {"page": 4, "labels": ["imza_beyannamesi"]},
            ]
        }
    )

    chunks = build_chunks(mapped, pages(4))

    assert [(chunk.chunk_id, chunk.pages) for chunk in chunks] == [
        ("annex_p1", [1]),
        ("annex_p2", [2]),
        ("annex_p4", [4]),
    ]
    assert all(chunk.supporting_only for chunk in chunks)


def test_context_uses_the_full_rules_span_for_each_window() -> None:
    mapped = page_map(
        {
            "company_name_line": "ÖRNEK A.Ş.",
            "structure_hints": ["A grubu", "B grubu"],
            "pages": [
                {"page": 1, "labels": ["rules"]},
                {"page": 2, "labels": ["rules"]},
                {"page": 3, "labels": ["rules"]},
            ],
        }
    )

    chunks = build_chunks(mapped, pages(3))

    assert "covers pages 1-2" in chunks[0].context_header
    assert "covers pages 2-3" in chunks[1].context_header
    assert all("rules section spanning pages 1-3" in chunk.context_header for chunk in chunks)
    assert all("A grubu; B grubu" in chunk.context_header for chunk in chunks)


def test_page_map_and_rendered_images_must_cover_the_same_pages() -> None:
    mapped = page_map({"pages": [{"page": 1, "labels": ["rules"]}]})

    with pytest.raises(ChunkerError, match=r"missing_images=\[1\]"):
        build_chunks(mapped, [])
    with pytest.raises(ChunkerError, match=r"extra_images=\[2\]"):
        build_chunks(mapped, [rendered_page(1), rendered_page(2)])


def test_duplicate_rendered_page_numbers_are_rejected() -> None:
    mapped = page_map({"pages": [{"page": 1, "labels": ["rules"]}]})

    with pytest.raises(ChunkerError, match="duplicate"):
        build_chunks(mapped, [rendered_page(1), rendered_page(1)])


def test_diagnostic_prints_chunk_identity_pages_and_support_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = check_chunker.main([str(FIXTURES / "nine_page.json")])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "chunks      7" in output
    assert "rules_p3-4" in output
    assert "annex_p9" in output
    assert "supporting" in output


def test_diagnostic_rejects_an_invalid_page_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "broken.json"
    fixture.write_text(json.dumps({"pages": []}), encoding="utf-8")

    assert check_chunker.main([str(fixture)]) == 1
    assert "FAILED" in capsys.readouterr().out
