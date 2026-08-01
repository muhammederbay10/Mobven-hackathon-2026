# ai/turkish.py
"""Turkish-aware comparison primitives: casing, company suffixes, IDs, and document dates."""

from __future__ import annotations

import re
import unicodedata
from datetime import date as Date
from types import MappingProxyType

# Python's str.lower() maps I→i and İ→"i"+U+0307, and str.upper() maps i→I. All three are wrong
# for Turkish, so the special pair is mapped explicitly before the generic case operation runs.
_TO_LOWER = MappingProxyType({ord("İ"): "i", ord("I"): "ı"})
_TO_UPPER = MappingProxyType({ord("i"): "İ", ord("ı"): "I"})

# Comparison form only: a scan that loses a cedilla must still match, so Turkish letters fold to
# ASCII. Never use the folded form for display, evidence, or audit — those keep the printed value.
_FOLD = MappingProxyType(
    {
        ord("ç"): "c",
        ord("ğ"): "g",
        ord("ı"): "i",
        ord("ö"): "o",
        ord("ş"): "s",
        ord("ü"): "u",
        ord("â"): "a",
        ord("î"): "i",
        ord("û"): "u",
    }
)

_NON_WORD = re.compile(r"[^0-9a-z]+")
_MASKED_ID = re.compile(r"\d{3}\*{6}\d{2}")  # mirrors MaskedNationalId in ai/schema.py

# Legal-form tokens, in normalized form, matched only as trailing token runs. Turkish company
# forms are a closed set defined by the TTK, which is why a table beats a judgment here.
_COMPANY_SUFFIXES: tuple[tuple[str, ...], ...] = (
    ("limited", "sirketi"),
    ("anonim", "sirketi"),
    ("kollektif", "sirketi"),
    ("komandit", "sirketi"),
    ("ltd", "sti"),
    ("a", "s"),
    ("limited",),
    ("anonim",),
    ("sirketi",),
    ("sirket",),
    ("ltd",),
    ("sti",),
    ("as",),
    ("sanayi",),
    ("san",),
    ("ticaret",),
    ("tic",),
    ("ve",),
)

_MONTHS = MappingProxyType(
    {
        "ocak": 1,
        "subat": 2,
        "mart": 3,
        "nisan": 4,
        "mayis": 5,
        "haziran": 6,
        "temmuz": 7,
        "agustos": 8,
        "eylul": 9,
        "ekim": 10,
        "kasim": 11,
        "aralik": 12,
    }
)

_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$")
_NAMED_DATE = re.compile(r"^(\d{1,2}) ([a-z]+) (\d{4})$")


def tr_lower(text: str) -> str:
    """Lowercases Turkish text without producing the dotted-i artefact."""

    return unicodedata.normalize("NFC", text).translate(_TO_LOWER).lower()


def tr_upper(text: str) -> str:
    """Uppercases Turkish text, keeping the dotted and dotless i distinct."""

    return unicodedata.normalize("NFC", text).translate(_TO_UPPER).upper()


def tr_normalize(text: str) -> str:
    """Reduces text to its comparison form: folded casing and diacritics, single-spaced words."""

    folded = tr_lower(text).translate(_FOLD)
    decomposed = unicodedata.normalize("NFKD", folded)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_NON_WORD.sub(" ", ascii_only).split())


def digits_only(text: str) -> str:
    """Keeps ASCII digits, so masked, spaced, and punctuated identifiers compare as numbers."""

    return re.sub(r"[^0-9]", "", text)


def name_equal(left: str, right: str) -> bool:
    """Strict equality after normalization. Never fuzzy: GUSEVA and CUSKYA must stay different."""

    normalized = tr_normalize(left)
    return bool(normalized) and normalized == tr_normalize(right)


def strip_company_suffix(name: str) -> str:
    """Returns the normalized distinctive core of a company name, for company comparison only."""

    tokens = tr_normalize(name).split()
    while tokens:
        suffix = _matching_suffix(tokens)
        if suffix is None:
            break
        remaining = tokens[: -len(suffix)]
        if not remaining:
            # A name made only of legal-form tokens keeps them: an empty core would match everything.
            break
        tokens = remaining
    return " ".join(tokens)


def _matching_suffix(tokens: list[str]) -> tuple[str, ...] | None:
    """Longest trailing legal-form token run, so 'limited sirketi' wins over 'sirketi'."""

    for suffix in sorted(_COMPANY_SUFFIXES, key=len, reverse=True):
        if len(tokens) >= len(suffix) and tuple(tokens[-len(suffix) :]) == suffix:
            return suffix
    return None


def company_equal(left: str, right: str) -> bool:
    """Company equality on distinctive cores: 'Ltd. Şti.' and 'Limited Şirketi' compare equal."""

    core = strip_company_suffix(left)
    return bool(core) and core == strip_company_suffix(right)


def masked_id_equal(left: str | None, right: str | None) -> bool:
    """Corroborating evidence only.

    A masked-ID match supports a matching name and can never replace one: two different people
    can share the six hidden digits. Callers must require name equality first.
    """

    if not (left and right):
        return False
    if not (_MASKED_ID.fullmatch(left) and _MASKED_ID.fullmatch(right)):
        return False
    return left == right


def parse_tr_date(text: str) -> Date:
    """Parses 14.03.2026, 14/03/2026, 14 Mart 2026, and ISO dates. Raises ValueError otherwise.

    Refuses ambiguous input such as two-digit years instead of guessing a century. Plausibility of
    a well-formed date is the validator's job, not the parser's.
    """

    raw = (text or "").strip()

    iso = _ISO_DATE.match(raw)
    if iso:
        return _build_date(int(iso[1]), int(iso[2]), int(iso[3]), text)

    numeric = _NUMERIC_DATE.match(raw)
    if numeric:
        return _build_date(int(numeric[3]), int(numeric[2]), int(numeric[1]), text)

    named = _NAMED_DATE.match(tr_normalize(raw))
    if named and named[2] in _MONTHS:
        return _build_date(int(named[3]), _MONTHS[named[2]], int(named[1]), text)

    raise ValueError(f"unrecognised Turkish date: {text!r}")


def _build_date(year: int, month: int, day: int, text: str) -> Date:
    try:
        return Date(year, month, day)
    except ValueError as error:
        raise ValueError(f"invalid Turkish date {text!r}: {error}") from error
