# ai/scripts/check_turkish.py
"""Prints worked examples of the Turkish comparison primitives and fails on any surprise."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.turkish import (  # noqa: E402
    company_equal,
    digits_only,
    masked_id_equal,
    name_equal,
    parse_tr_date,
    strip_company_suffix,
    tr_normalize,
    tr_upper,
)

LABEL_WIDTH = 58
VALUE_WIDTH = 26


@dataclass(frozen=True)
class Example:
    """One call, what it produced, and what it must produce."""

    label: str
    produced: Any
    expected: Any

    @property
    def ok(self) -> bool:
        return self.produced == self.expected


@dataclass(frozen=True)
class Section:
    title: str
    note: str | None
    examples: list[Example]


def call(
    func: Callable[..., Any], *args: Any, expected: Any, name: str | None = None
) -> Example:
    """Builds an example whose label is the call itself, so the output reads like source."""

    arguments = ", ".join(repr(argument) for argument in args)
    return Example(f"{name or func.__name__}({arguments})", func(*args), expected)


def parsed(text: str) -> str:
    """Renders parse_tr_date's outcome as a printable value instead of a traceback."""

    try:
        return f"parsed {parse_tr_date(text)}"
    except ValueError:
        return "refused"


def sections() -> list[Section]:
    stdlib_collision = "ALİ YILMAZ".lower() == "Ali Yılmaz".lower()
    return [
        Section(
            title="casing — why str.lower() is not enough",
            note=(
                f"  stdlib     'ALİ YILMAZ'.lower() = {'ALİ YILMAZ'.lower()!r}\n"
                f"  stdlib     'Ali Yılmaz'.lower() = {'Ali Yılmaz'.lower()!r}\n"
                f"  yetkicheck tr_normalize(both)  = {tr_normalize('ALİ YILMAZ')!r}"
            ),
            examples=[
                Example("'ALİ YILMAZ'.lower() == 'Ali Yılmaz'.lower()", stdlib_collision, False),
                call(tr_normalize, "ALİ YILMAZ", expected="ali yilmaz"),
                call(tr_normalize, "Ali Yılmaz", expected="ali yilmaz"),
                call(tr_upper, "Ali Yılmaz", expected="ALİ YILMAZ"),
                call(tr_normalize, "IŞIK", expected="isik"),
            ],
        ),
        Section(
            title="person names — strict equality, never fuzzy",
            note=None,
            examples=[
                call(name_equal, "ALİ YILMAZ", "Ali Yılmaz", expected=True),
                call(name_equal, "AYŞE DEMİR", "Ayse Demir", expected=True),
                call(name_equal, "GUSEVA", "CUSKYA", expected=False),
                call(name_equal, "Ali Yılmaz", "Ali Yılmax", expected=False),
                call(name_equal, "Kemal Öz", "Kemal Özer", expected=False),
                call(name_equal, "", "", expected=False),
            ],
        ),
        Section(
            title="company names — trailing legal-form tokens only",
            note=None,
            examples=[
                call(strip_company_suffix, "ABC Teknoloji Ltd. Şti.", expected="abc teknoloji"),
                call(strip_company_suffix, "ABC TEKNOLOJİ LİMİTED ŞİRKETİ", expected="abc teknoloji"),
                call(strip_company_suffix, "Zeta İnşaat San. ve Tic. A.Ş.", expected="zeta insaat"),
                call(
                    strip_company_suffix,
                    "Sanayi ve Ticaret Bankası A.Ş.",
                    expected="sanayi ve ticaret bankasi",
                ),
                call(strip_company_suffix, "San Marino Turizm A.Ş.", expected="san marino turizm"),
                call(
                    company_equal,
                    "ABC Teknoloji Ltd. Şti.",
                    "ABC Teknoloji Yazılım Ltd. Şti.",
                    expected=False,
                ),
            ],
        ),
        Section(
            title="identifiers — masked IDs corroborate, they never prove",
            note="  a masked-ID match with a name mismatch can never make identity_match green",
            examples=[
                call(digits_only, "0123 4567 8900 0017", expected="0123456789000017"),
                call(masked_id_equal, "123******01", "123******01", expected=True),
                call(masked_id_equal, "123******01", "123******02", expected=False),
                call(masked_id_equal, "12345678901", "12345678901", expected=False),
            ],
        ),
        Section(
            title="dates — one day, several spellings, explicit refusals",
            note=None,
            examples=[
                call(parsed, "14.03.2026", expected="parsed 2026-03-14", name="parse_tr_date"),
                call(parsed, "14/03/2026", expected="parsed 2026-03-14", name="parse_tr_date"),
                call(parsed, "14 Mart 2026", expected="parsed 2026-03-14", name="parse_tr_date"),
                call(parsed, "1 Ağustos 2026", expected="parsed 2026-08-01", name="parse_tr_date"),
                call(parsed, "14.03.26", expected="refused", name="parse_tr_date"),
                call(parsed, "31.02.2026", expected="refused", name="parse_tr_date"),
                call(parsed, "03/14/2026", expected="refused", name="parse_tr_date"),
            ],
        ),
    ]


def render(example: Example) -> str:
    row = f"  {example.label:<{LABEL_WIDTH}}  {str(example.produced):<{VALUE_WIDTH}}"
    if example.ok:
        return f"{row}  OK"
    return f"{row}  FAILED, expected {example.expected!r}"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("YetkiCheck — Turkish comparison primitives (ai/turkish.py)\n")

    failures = 0
    for section in sections():
        print(section.title)
        if section.note:
            print(section.note)
        for example in section.examples:
            print(render(example))
            failures += not example.ok
        print()

    if failures:
        print(f"FAILED — {failures} example(s) did not match")
        return 1
    print("ALL EXAMPLES MATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
