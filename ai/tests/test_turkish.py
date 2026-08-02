# ai/tests/test_turkish.py
"""Covers the Turkish comparison primitives, including the casing traps that fail silently."""

from __future__ import annotations

from datetime import date as Date

import pytest

from ai.schema import MaskedNationalId
from ai.turkish import (
    canonicalize_group_code,
    canonicalize_masked_id,
    company_equal,
    digits_only,
    masked_id_equal,
    name_equal,
    parse_tr_date,
    strip_company_suffix,
    tr_lower,
    tr_normalize,
    tr_upper,
)

TURKISH_MONTHS = (
    ("Ocak", 1),
    ("Şubat", 2),
    ("Mart", 3),
    ("Nisan", 4),
    ("Mayıs", 5),
    ("Haziran", 6),
    ("Temmuz", 7),
    ("Ağustos", 8),
    ("Eylül", 9),
    ("Ekim", 10),
    ("Kasım", 11),
    ("Aralık", 12),
)


def test_python_casefold_is_the_reason_this_module_exists() -> None:
    # The reference failure: stdlib lower() turns İ into i + U+0307 and I into a dotted i.
    assert "ALİ YILMAZ".lower() != "Ali Yılmaz".lower()

    assert tr_normalize("ALİ YILMAZ") == tr_normalize("Ali Yılmaz") == "ali yilmaz"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("A Grubu İmza Yetkilileri", "a"),
        ("I. Derece", "1"),
        ("1. derece imza yetkilisi", "1"),
        ("Birinci Derece", "1"),
        ("VI. Derece Yetkilileri", "6"),
    ],
)
def test_signature_group_aliases_have_one_join_key(printed: str, expected: str) -> None:
    assert canonicalize_group_code(printed) == expected


def test_tr_lower_and_tr_upper_keep_the_two_letter_i_forms_apart() -> None:
    assert tr_lower("ALİ YILMAZ") == "ali yılmaz"
    assert tr_upper("Ali Yılmaz") == "ALİ YILMAZ"
    assert tr_lower("IŞIK") == "ışık"
    assert tr_upper("ışık") == "IŞIK"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("ALİ YILMAZ", "Ali Yılmaz"),
        ("AYŞE DEMİR", "Ayşe Demir"),
        ("Ayse Demir", "Ayşe Demir"),  # a scan that lost the cedilla still matches
        ("  Kemal   ÖZ ", "Kemal Öz"),
        ("Mehmet KAYA.", "mehmet kaya"),
    ],
)
def test_name_equal_accepts_the_same_person_written_differently(left: str, right: str) -> None:
    assert name_equal(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("GUSEVA", "CUSKYA"),  # the spike's garbled-name failure must never collapse
        ("Ali Yılmaz", "Ali Yılmax"),
        ("Ali Yılmaz", "Ayşe Demir"),
        ("Kemal Öz", "Kemal Özer"),
        ("Mehmet Kaya", "Mehmet"),
    ],
)
def test_name_equal_refuses_near_misses(left: str, right: str) -> None:
    assert not name_equal(left, right)


def test_name_equal_never_matches_an_unreadable_name() -> None:
    assert not name_equal("", "")
    assert not name_equal("***", "???")


@pytest.mark.parametrize(
    "written",
    [
        "ABC Teknoloji Ltd. Şti.",
        "ABC TEKNOLOJİ LİMİTED ŞİRKETİ",
        "ABC Teknoloji Limited Şirketi",
        "ABC Teknoloji Ltd.Şti.",
        "ABC TEKNOLOJI LTD ŞTI",
    ],
)
def test_company_legal_forms_reduce_to_the_same_core(written: str) -> None:
    assert strip_company_suffix(written) == "abc teknoloji"
    assert company_equal(written, "ABC Teknoloji Ltd. Şti.")


def test_company_suffix_stripping_handles_the_long_anonim_form() -> None:
    assert strip_company_suffix("Zeta İnşaat Sanayi ve Ticaret Anonim Şirketi") == (
        "zeta insaat sanayi ve ticaret"
    )
    assert company_equal(
        "Zeta İnşaat Sanayi ve Ticaret Anonim Şirketi", "Zeta İnşaat San. ve Tic. A.Ş."
    )


@pytest.mark.parametrize(
    ("written", "core"),
    [
        ("Sanayi ve Ticaret Bankası A.Ş.", "sanayi ve ticaret bankasi"),
        ("Ve Ve Gıda San. Tic. Ltd. Şti.", "ve ve gida sanayi ticaret"),
        ("San Marino Turizm A.Ş.", "san marino turizm"),
        ("Kuzey ve Güney Lojistik Limited Şirketi", "kuzey ve guney lojistik"),
    ],
)
def test_suffix_tokens_inside_a_name_survive(written: str, core: str) -> None:
    assert strip_company_suffix(written) == core


def test_a_name_made_only_of_legal_form_tokens_keeps_a_core() -> None:
    # An empty core would compare equal to every other empty core, which is worse than not matching.
    assert strip_company_suffix("Sanayi ve Ticaret A.Ş.") != ""
    assert not company_equal("Sanayi ve Ticaret A.Ş.", "San. Tic. Ltd. Şti.")


def test_different_companies_never_compare_equal() -> None:
    assert not company_equal("ABC Teknoloji Ltd. Şti.", "Zeta İnşaat San. ve Tic. A.Ş.")
    assert not company_equal("ABC Teknoloji Ltd. Şti.", "ABC Teknoloji Yazılım Ltd. Şti.")
    assert not company_equal("ABC Ticaret A.Ş.", "ABC A.Ş.")
    assert not company_equal("ABC Ticaret", "ABC")


def test_digits_only_ignores_formatting() -> None:
    assert digits_only("0123456789000017") == "0123456789000017"
    assert digits_only("0123 4567 8900 0017") == "0123456789000017"
    assert digits_only("VKN: 1.234.567.890") == "1234567890"
    assert digits_only("123******01") == "12301"


def test_masked_id_equality_accepts_source_mask_lengths() -> None:
    assert masked_id_equal("123******01", "123******01")
    assert masked_id_equal("123********01", "123******01")
    assert canonicalize_masked_id("123********01") == "123******01"
    assert not masked_id_equal("123******01", "123******02")
    assert masked_id_equal("123***01", "123***01")
    assert not masked_id_equal("12345678901", "12345678901")
    assert not masked_id_equal(None, "123******01")
    assert not masked_id_equal("", "")


def test_masked_id_pattern_agrees_with_the_frozen_schema() -> None:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(MaskedNationalId)
    valid = adapter.validate_python("123******01")

    assert masked_id_equal(valid, "123******01")


def test_masked_id_match_cannot_stand_in_for_a_name_match() -> None:
    # Same hidden digits, different people: identity_match must stay red on the name alone.
    assert masked_id_equal("123******01", "123******01")
    assert not name_equal("GUSEVA", "CUSKYA")
    # The module offers no combined helper, so no caller can shortcut the name comparison.
    import ai.turkish as turkish

    assert not [name for name in dir(turkish) if "identity" in name]


@pytest.mark.parametrize(
    "written",
    ["14.03.2026", "14/03/2026", "14-03-2026", "14 Mart 2026", "14 MART 2026", "2026-03-14"],
)
def test_every_supported_date_format_parses_to_the_same_day(written: str) -> None:
    assert parse_tr_date(written) == Date(2026, 3, 14)


@pytest.mark.parametrize(("month_name", "month"), TURKISH_MONTHS)
def test_all_twelve_turkish_month_names_parse(month_name: str, month: int) -> None:
    assert parse_tr_date(f"1 {month_name} 2026") == Date(2026, month, 1)


@pytest.mark.parametrize(
    "written",
    [
        "14.03.26",  # two-digit year: which century?
        "31.02.2026",
        "03/14/2026",  # month 14 — refuse rather than swap day and month
        "14 Marc 2026",
        "14 Mart",
        "2026",
        "",
        "   ",
        "yevmiye 08912",
    ],
)
def test_ambiguous_or_invalid_dates_are_refused(written: str) -> None:
    with pytest.raises(ValueError):
        parse_tr_date(written)


def test_parse_tr_date_reports_what_it_refused() -> None:
    with pytest.raises(ValueError, match="unrecognised Turkish date: '14.03.26'"):
        parse_tr_date("14.03.26")

    with pytest.raises(ValueError, match="invalid Turkish date"):
        parse_tr_date("31.02.2026")


def test_diagnostic_script_reports_every_example_as_matching(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai.scripts.check_turkish import main

    exit_code = main()

    assert exit_code == 0
    assert "ALL EXAMPLES MATCH" in capsys.readouterr().out


def test_primitives_are_deterministic_and_side_effect_free() -> None:
    written = "ABC Teknoloji Ltd. Şti."

    assert strip_company_suffix(written) == strip_company_suffix(written)
    assert written == "ABC Teknoloji Ltd. Şti."
