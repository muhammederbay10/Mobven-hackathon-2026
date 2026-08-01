"""Bank-side normalization for deterministic joins, never identity proof."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9çğıöşü]+")


def normalize_name(value: str) -> str:
    value = value.strip().replace("I", "ı").replace("İ", "i").lower()
    value = unicodedata.normalize("NFKC", value)
    return " ".join(part for part in _NON_WORD.sub(" ", value).split() if part)
