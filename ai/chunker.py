# ai/chunker.py
"""Groups rendered pages into deterministic, section-aware extraction chunks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

if __package__:
    from .render import PageImages
    from .schema import PageClassification, PageLabel, PageMap
else:  # scripts may import this module from inside ai/
    from render import PageImages
    from schema import PageClassification, PageLabel, PageMap


RULE_WINDOW_SIZE = 4
ChunkAgent = Literal["appointments", "rules", "specimens", "annex", "review"]

APPOINTMENT_RIDE_ALONG_LABELS = frozenset(
    {PageLabel.IDENTITY_HEADER, PageLabel.DAYANAK, PageLabel.NOTARY_BLOCK}
)
ANNEX_LABELS = frozenset(
    {
        PageLabel.IC_YONERGE_ANNEX,
        PageLabel.BOARD_RESOLUTION_ANNEX,
        PageLabel.GAZETTE_ANNEX,
        PageLabel.IMZA_BEYANNAMESI,
    }
)
RULE_CONTINUATION_BLOCKERS = frozenset(
    {
        PageLabel.SPECIMENS,
        PageLabel.GAZETTE_ANNEX,
        PageLabel.IMZA_BEYANNAMESI,
        PageLabel.COVER_OR_BLANK,
    }
)


class ChunkerError(ValueError):
    """Raised when the page map and rendered pages cannot be reconciled safely."""


@dataclass(frozen=True)
class Chunk:
    """One focused extractor request containing high-resolution page images."""

    chunk_id: str
    agent: ChunkAgent
    pages: list[int]
    images: list[bytes]
    context_header: str
    supporting_only: bool


def build_chunks(page_map: PageMap, rendered_pages: Sequence[PageImages]) -> list[Chunk]:
    """Builds typed chunks without dropping classified or uncertain document content."""

    images = _extract_images(page_map, rendered_pages)
    classifications = {page.page: page for page in page_map.pages}
    chunks: list[Chunk] = []

    appointment_section = _pages_with_label(classifications.values(), PageLabel.APPOINTMENTS)
    appointment_pages = sorted(
        set(appointment_section)
        | set(_pages_with_any_label(classifications.values(), APPOINTMENT_RIDE_ALONG_LABELS))
    )
    if appointment_pages:
        chunks.append(
            _make_chunk(
                page_map,
                images,
                agent="appointments",
                pages=appointment_pages,
                section_pages=appointment_section or appointment_pages,
            )
        )

    rule_pages = _rule_section_pages(classifications)
    for section_pages in _contiguous_runs(rule_pages):
        windows = _overlapping_rule_windows(section_pages)
        for index, window in enumerate(windows):
            focus_pages = window if index == len(windows) - 1 else window[:-1]
            chunks.append(
                _make_chunk(
                    page_map,
                    images,
                    agent="rules",
                    pages=window,
                    section_pages=section_pages,
                    focus_pages=focus_pages,
                )
            )

    specimen_pages = _pages_with_label(classifications.values(), PageLabel.SPECIMENS)
    for page_number in specimen_pages:
        chunks.append(
            _make_chunk(
                page_map,
                images,
                agent="specimens",
                pages=[page_number],
                section_pages=specimen_pages,
            )
        )

    for page_run in _annex_runs(classifications.values()):
        chunks.append(
            _make_chunk(
                page_map,
                images,
                agent="annex",
                pages=page_run,
                section_pages=page_run,
                supporting_only=True,
            )
        )

    # Unknown content goes straight to review. It deliberately remains a chunk even when the
    # same page also belongs to a known section, so uncertainty is never hidden by a good label.
    unknown_pages = _pages_with_label(classifications.values(), PageLabel.OTHER_UNKNOWN)
    for page_number in unknown_pages:
        chunks.append(
            _make_chunk(
                page_map,
                images,
                agent="review",
                pages=[page_number],
                section_pages=[page_number],
                supporting_only=True,
            )
        )

    return chunks


def _extract_images(
    page_map: PageMap, rendered_pages: Sequence[PageImages]
) -> dict[int, bytes]:
    image_by_page = {page.page_no: page.extract_png for page in rendered_pages}
    if len(image_by_page) != len(rendered_pages):
        raise ChunkerError("rendered pages contain duplicate page numbers")

    mapped = {page.page for page in page_map.pages}
    rendered = set(image_by_page)
    if mapped != rendered:
        missing = sorted(mapped - rendered)
        extra = sorted(rendered - mapped)
        raise ChunkerError(
            f"page map and rendered pages differ (missing_images={missing}, extra_images={extra})"
        )
    return image_by_page


def _pages_with_label(
    pages: Iterable[PageClassification], label: PageLabel
) -> list[int]:
    return [page.page for page in pages if label in page.labels]


def _pages_with_any_label(
    pages: Iterable[PageClassification], labels: frozenset[PageLabel]
) -> list[int]:
    return [page.page for page in pages if any(label in labels for label in page.labels)]


def _rule_section_pages(
    classifications: dict[int, PageClassification],
) -> list[int]:
    """Expands explicit rule labels across continuation chains without swallowing later sections."""

    explicit = set(_pages_with_label(classifications.values(), PageLabel.RULES))
    expanded = set(explicit)
    for page_number in explicit:
        previous = page_number - 1
        while (
            previous in classifications
            and classifications[previous].continues_on_next
            and _can_extend_rule_section(classifications[previous])
        ):
            expanded.add(previous)
            previous -= 1

        page = classifications[page_number]
        next_page = classifications.get(page_number + 1)
        if (
            page.continues_on_next
            and next_page is not None
            and _can_extend_rule_section(next_page)
        ):
            expanded.add(page_number + 1)
    return sorted(expanded)


def _can_extend_rule_section(page: PageClassification) -> bool:
    return PageLabel.RULES in page.labels or not any(
        label in RULE_CONTINUATION_BLOCKERS for label in page.labels
    )


def _overlapping_rule_windows(page_numbers: Sequence[int]) -> list[list[int]]:
    if len(page_numbers) <= RULE_WINDOW_SIZE:
        return [list(page_numbers)] if page_numbers else []
    return [
        list(page_numbers[index : index + RULE_WINDOW_SIZE])
        for index in range(0, len(page_numbers) - 1, RULE_WINDOW_SIZE - 1)
    ]


def _contiguous_runs(page_numbers: Sequence[int]) -> list[list[int]]:
    if not page_numbers:
        return []
    runs = [[page_numbers[0]]]
    for page_number in page_numbers[1:]:
        if page_number == runs[-1][-1] + 1:
            runs[-1].append(page_number)
        else:
            runs.append([page_number])
    return runs


def _annex_runs(pages: Iterable[PageClassification]) -> list[list[int]]:
    runs: list[list[int]] = []
    current_pages: list[int] = []
    current_labels: frozenset[PageLabel] = frozenset()

    for page in pages:
        labels = frozenset(label for label in page.labels if label in ANNEX_LABELS)
        same_section = (
            bool(current_pages)
            and page.page == current_pages[-1] + 1
            and labels == current_labels
        )
        if not labels:
            if current_pages:
                runs.append(current_pages)
                current_pages = []
                current_labels = frozenset()
            continue
        if same_section:
            current_pages.append(page.page)
            continue
        if current_pages:
            runs.append(current_pages)
        current_pages = [page.page]
        current_labels = labels

    if current_pages:
        runs.append(current_pages)
    return runs


def _make_chunk(
    page_map: PageMap,
    images: dict[int, bytes],
    *,
    agent: ChunkAgent,
    pages: Sequence[int],
    section_pages: Sequence[int],
    focus_pages: Sequence[int] | None = None,
    supporting_only: bool = False,
) -> Chunk:
    ordered_pages = list(pages)
    return Chunk(
        chunk_id=f"{agent}_p{_page_token(ordered_pages)}",
        agent=agent,
        pages=ordered_pages,
        images=[images[page] for page in ordered_pages],
        context_header=_context_header(
            page_map,
            agent,
            ordered_pages,
            section_pages,
            focus_pages or ordered_pages,
        ),
        supporting_only=supporting_only,
    )


def _context_header(
    page_map: PageMap,
    agent: ChunkAgent,
    pages: Sequence[int],
    section_pages: Sequence[int],
    focus_pages: Sequence[int],
) -> str:
    company = page_map.company_name_line or "UNREADABLE"
    hints = "; ".join(
        hint.strip().rstrip(".;") for hint in page_map.structure_hints if hint.strip()
    )
    hint_text = hints or "No structure hints"
    section = "unclassified" if agent == "review" else agent
    ownership = ""
    if agent == "rules" and list(focus_pages) != list(pages):
        context_only = [page for page in pages if page not in focus_pages]
        ownership = (
            f" Emit only clauses whose first quoted words begin on pages "
            f"{_format_pages(focus_pages)}; pages {_format_pages(context_only)} are "
            "continuation context only."
        )
    return (
        f"Document: imza sirküleri of {company}. {hint_text}. "
        f"This request covers pages {_format_pages(pages)} of the {section} section "
        f"spanning pages {_format_span(section_pages)}.{ownership} "
        "Page numbers below are absolute."
    )


def _page_token(page_numbers: Sequence[int]) -> str:
    if len(page_numbers) == 1:
        return str(page_numbers[0])
    if _is_contiguous(page_numbers):
        return f"{page_numbers[0]}-{page_numbers[-1]}"
    return "+".join(str(page) for page in page_numbers)


def _format_pages(page_numbers: Sequence[int]) -> str:
    if len(page_numbers) == 1:
        return str(page_numbers[0])
    if _is_contiguous(page_numbers):
        return f"{page_numbers[0]}-{page_numbers[-1]}"
    return ", ".join(str(page) for page in page_numbers)


def _format_span(page_numbers: Sequence[int]) -> str:
    if len(page_numbers) == 1:
        return str(page_numbers[0])
    return f"{min(page_numbers)}-{max(page_numbers)}"


def _is_contiguous(page_numbers: Sequence[int]) -> bool:
    return all(right == left + 1 for left, right in zip(page_numbers, page_numbers[1:]))
