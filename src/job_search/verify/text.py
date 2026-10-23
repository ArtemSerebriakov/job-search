"""Small text helpers shared by the rules."""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+|\s+[•·▪◦]\s*|^\s*[-*]\s+", re.MULTILINE)


def sentences(text: str) -> list[str]:
    """Split posting text into sentences / bullet items."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]


def snippet(text: str, match: re.Match, width: int = 60) -> str:
    """Up to `width` chars of context on each side of a regex match, on one line."""
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    out = re.sub(r"\s+", " ", text[start:end]).strip()
    return ("…" if start else "") + out + ("…" if end < len(text) else "")


_OPTIONAL = re.compile(
    r"\b(nice[- ]to[- ]have|a plus|is a plus|an advantage|advantageous|bonus|preferred|preferably|"
    r"desirable|ideally|not required|not necessary|not a must|no need|"
    r"von vorteil|wünschenswert|wuenschenswert|ein plus|idealerweise|nicht erforderlich|keine voraussetzung|"
    r"nicht notwendig|optional)\b",
    re.IGNORECASE,
)


def is_optional(sentence: str) -> bool:
    """True if the sentence frames its requirement as nice-to-have / not required."""
    return bool(_OPTIONAL.search(sentence))
