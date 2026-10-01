"""Deadline extraction and urgency helpers. Pure functions (no I/O)."""
from __future__ import annotations

import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_ORD = r"(?:st|nd|rd|th)?"

KEYWORDS = r"(?:deadline|last\s+date|closing\s+date|apply\s+(?:by|before|within)|application\s+(?:deadline|closes?)|submit(?:ted)?\s+(?:by|before)|on\s+or\s+before|due\s+date|expires?|valid\s+(?:till|until)|(?:no\s+later\s+than)|before|until|till)"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b(\d{{1,2}}){_ORD}\s*(?:of\s+)?{_MON}\.?,?\s*(\d{{4}})?\b", re.I), "dmy_text"),
    (re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}}){_ORD}(?:,?\s*(\d{{4}}))?\b", re.I), "mdy_text"),
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b"), "dmy_num"),
]


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _find_dates(segment: str, today: date) -> list[tuple[int, date]]:
    out: list[tuple[int, date]] = []
    for pat, kind in _PATTERNS:
        for m in pat.finditer(segment):
            g = m.groups()
            dt: date | None = None
            if kind == "dmy_text":
                d, mon, y = int(g[0]), MONTHS[g[1][:3].lower()], g[2]
                dt = _resolve(d, mon, int(y) if y else None, today)
            elif kind == "mdy_text":
                mon, d, y = MONTHS[g[0][:3].lower()], int(g[1]), g[2]
                dt = _resolve(d, mon, int(y) if y else None, today)
            elif kind == "iso":
                dt = _mk(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "dmy_num":
                a, b, y = int(g[0]), int(g[1]), int(g[2])
                y = y + 2000 if y < 100 else y
                # Day-first by default (Bangladesh/UK/EU convention); fall back to month-first if impossible.
                dt = _mk(y, b, a) or _mk(y, a, b)
            if dt:
                out.append((m.start(), dt))
    return sorted(out)


def _resolve(day: int, month: int, year: int | None, today: date) -> date | None:
    if year is not None:
        return _mk(year, month, day)
    cand = _mk(today.year, month, day)
    if cand and cand < today and (today - cand).days > 30:
        cand = _mk(today.year + 1, month, day)  # no year given: next occurrence
    return cand


def extract_deadline(text: str, today: date | None = None) -> date | None:
    """Return the application deadline only if a date appears right after a deadline cue.

    We intentionally return None rather than guess when no cue is present.
    """
    today = today or date.today()
    best: date | None = None
    for kw in re.finditer(KEYWORDS, text, re.I):
        window = text[kw.end(): kw.end() + 90]
        # stop at sentence break that precedes the date by a lot
        dates = _find_dates(window, today)
        if dates:
            cand = dates[0][1]
            if best is None or cand > best:
                best = cand
    return best


def days_remaining(deadline: date | None, today: date | None = None) -> int | None:
    if deadline is None:
        return None
    return (deadline - (today or date.today())).days


def urgency_label(days: int | None) -> str:
    if days is None:
        return "none"
    if days < 0:
        return "expired"
    if days <= 3:
        return "critical"
    if days <= 7:
        return "soon"
    return "ok"
