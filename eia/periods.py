"""Indian fiscal-period parsing. FY2024 = 1 Apr 2023 – 31 Mar 2024. Q1 = Apr–Jun."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

_FY_SPAN = re.compile(r"\b(?:FY\s?'?|F\.Y\.\s?)?(20\d{2})\s?[-–/]\s?(\d{2}|20\d{2})\b", re.I)   # 2023-24, FY 2023-24
_FY_SHORT = re.compile(r"\bFY\s?'?(\d{2}|20\d{2})\b(?!\s?[-–/]\s?\d)", re.I)                       # FY24, FY2024
_QTR = re.compile(r"\b(Q[1-4])\s?[- ]?\s?FY\s?'?(\d{2}|20\d{2})\b(?!\s?[-–/]\s?\d)", re.I)                          # Q2FY25, Q2 FY 2025
_QTR2 = re.compile(r"\b(Q[1-4])\s?[- ]?\s?(?:of\s+)?(?:FY\s?)?(20\d{2})\s?[-–/]\s?(\d{2})\b", re.I)  # Q2 2024-25
_ENDED = re.compile(
    r"(quarter|half[\s-]year|nine\s+months|year|period|months)\s+ended\s+(?:on\s+)?"
    r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9}),?\s+(20\d{2})|([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(20\d{2}))",
    re.I)
_ASOF = re.compile(
    r"\b(?:as\s+(?:on|of|at))\s+(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9}),?\s+(20\d{2})|([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(20\d{2}))",
    re.I)
_TARGET_YEAR = re.compile(
    r"\bby\s+(?:the\s+end\s+of\s+)?(?:FY\s?'?(20\d{2}|\d{2})|(20\d{2}))(?:\s?[-–]\s?(\d{2}))?\b(?!\s*%)", re.I)


def _yr(s: str) -> int:
    y = int(s)
    return 2000 + y if y < 100 else y


def fy_label(fy: int) -> str:
    return f"FY{fy}"


def quarter_label(q: int, fy: int) -> str:
    return f"Q{q}FY{fy}"


def fy_from_date(d: date) -> int:
    return d.year + 1 if d.month >= 4 else d.year


def quarter_from_month(month: int) -> int:
    return {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[month]


def period_end(period: str) -> Optional[str]:
    """ISO end date for FYyyyy / QnFYyyyy labels."""
    m = re.fullmatch(r"FY(\d{4})", period or "")
    if m:
        return date(int(m.group(1)), 3, 31).isoformat()
    m = re.fullmatch(r"Q([1-4])FY(\d{4})", period or "")
    if m:
        q, fy = int(m.group(1)), int(m.group(2))
        ends = {1: (fy - 1, 6, 30), 2: (fy - 1, 9, 30), 3: (fy - 1, 12, 31), 4: (fy, 3, 31)}
        y, mo, d = ends[q]
        return date(y, mo, d).isoformat()
    return None


def period_sort_key(period: str) -> tuple[int, int]:
    m = re.fullmatch(r"FY(\d{4})", period or "")
    if m:
        return int(m.group(1)), 5
    m = re.fullmatch(r"Q([1-4])FY(\d{4})", period or "")
    if m:
        return int(m.group(2)), int(m.group(1))
    return 0, 0


def is_annual(period: str) -> bool:
    return bool(re.fullmatch(r"FY\d{4}", period or ""))


def is_quarter(period: str) -> bool:
    return bool(re.fullmatch(r"Q[1-4]FY\d{4}", period or ""))


def _date_from_parts(day, mon, year) -> Optional[date]:
    try:
        return date(int(year), MONTHS[mon[:3].lower()], int(day))
    except (KeyError, ValueError, TypeError):
        return None


_QTR_WORD = re.compile(r"\b(first|second|third|fourth)\s+quarter\s+(?:of\s+)?(?:the\s+)?(?:FY|financial\s+year)?\s*'?"
                       r"(20\d{2})\s?[-–/]\s?(\d{2}|20\d{2})\b", re.I)
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}


def parse_period(text: str) -> Optional[str]:
    """Extract the first explicit period mention in text. Returns FYyyyy / QnFYyyyy or None."""
    if not text:
        return None
    m = _QTR.search(text)
    if m:
        return quarter_label(int(m.group(1)[1]), _yr(m.group(2)))
    m = _QTR2.search(text)
    if m:
        return quarter_label(int(m.group(1)[1]), _yr(m.group(2)) + 1)
    m = _QTR_WORD.search(text)
    if m:
        return quarter_label(_ORD[m.group(1).lower()], int(m.group(2)) + 1)
    m = _ENDED.search(text)
    if m:
        kind = m.group(1).lower()
        d = _date_from_parts(m.group(2), m.group(3), m.group(4)) if m.group(2) else \
            _date_from_parts(m.group(6), m.group(5), m.group(7))
        if d:
            fy = fy_from_date(d)
            if kind.startswith("quarter"):
                return quarter_label(quarter_from_month(d.month), fy)
            if kind.startswith("year") and d.month == 3:
                return fy_label(fy)
            if kind.startswith("year"):
                return fy_label(fy)
            # half-year / nine-months / period: no canonical label; skip
    m = _FY_SPAN.search(text)
    if m:
        start = int(m.group(1))
        end = _yr(m.group(2)) if len(m.group(2)) == 4 else (start // 100) * 100 + int(m.group(2))
        if end == start + 1:
            return fy_label(end)
    m = _FY_SHORT.search(text)
    if m:
        return fy_label(_yr(m.group(1)))
    return None


def parse_asof(text: str) -> Optional[str]:
    """'as on 31 March 2024' -> FY2024 (point-in-time maps to the FY / quarter it closes)."""
    m = _ASOF.search(text or "")
    if not m:
        return None
    d = _date_from_parts(m.group(1), m.group(2), m.group(3)) if m.group(1) else \
        _date_from_parts(m.group(5), m.group(4), m.group(6))
    if not d:
        return None
    fy = fy_from_date(d)
    if d.month == 3:
        return fy_label(fy)
    return quarter_label(quarter_from_month(d.month), fy)


def parse_target_year(text: str) -> Optional[int]:
    m = _TARGET_YEAR.search(text or "")
    if not m:
        return None
    y = _yr(m.group(1) or m.group(2))
    if m.group(3):  # fiscal span "2029-30" -> FY2030
        y = (y // 100) * 100 + int(m.group(3))
    return y if 2020 <= y <= 2060 else None


def all_periods_in(text: str) -> list[str]:
    """Ordered list of period labels appearing in a line (used for table headers)."""
    found: list[tuple[int, int, str]] = []
    for rx, fn in ((_QTR, lambda m: quarter_label(int(m.group(1)[1]), _yr(m.group(2)))),
                   (_FY_SPAN, lambda m: fy_label(_yr(m.group(2)) if len(m.group(2)) == 4
                                                 else (int(m.group(1)) // 100) * 100 + int(m.group(2)))),
                   (_FY_SHORT, lambda m: fy_label(_yr(m.group(1))))):
        for m in rx.finditer(text):
            # skip tokens overlapping an already captured (more specific) token
            if any(s <= m.start() < e or s < m.end() <= e for s, e, _ in found):
                continue
            try:
                found.append((m.start(), m.end(), fn(m)))
            except Exception:
                continue
    found.sort()
    return [p for _, _, p in found]


# --- table-header column tokens --------------------------------------------------------------------
# Header tokens map to a period label, or to None for a recognised column that has no canonical label
# (nine months / half year / ambiguous date). None keeps column positions aligned with row values.

_MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_KIND = (r"(quarter|three\s+months|3\s+months|year|twelve\s+months|12\s+months|half[\s-]year|six\s+months|"
         r"6\s+months|nine\s+months|9\s+months|period)")
_ENDED_NUMERIC = re.compile(rf"{_KIND}\s+ended\s+(?:on\s+)?(\d{{1,2}})[-./](\d{{1,2}})[-./](20\d{{2}})", re.I)
_ENDED_TEXT = re.compile(rf"{_KIND}\s+ended\s+(?:on\s+)?(?:(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON},?\s+(20\d{{2}})|"
                         rf"{_MON}\s+(\d{{1,2}}),?\s+(20\d{{2}}))", re.I)
_MON_YEAR = re.compile(rf"\b{_MON}[\s'’-]*(20\d{{2}}|\d{{2}})\b", re.I)
_BARE_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
_QTR_SHORT_SPAN = re.compile(r"\bQ([1-4])\s*(?:FY\s*)?'?(\d{2})\s?[-–/]\s?(\d{2})\b", re.I)
_SHORT_SPAN = re.compile(r"(?<![\d./-])(?:FY\s*'?)?(\d{2})\s?[-–/]\s?(\d{2})(?![\d./-])", re.I)
_GROWTH_COL = re.compile(r"%\s*(?:growth|change|chg)|\b(?:yoy|qoq|y-o-y|q-o-q)\b\s*%?|\bgrowth\s*\(?%\)?|\bchange\s*\(?%\)?",
                         re.I)


def _label_for(kind: str, d: date) -> Optional[str]:
    k = kind.lower()
    if k.startswith(("quarter", "three", "3")):
        return quarter_label(quarter_from_month(d.month), fy_from_date(d))
    if k.startswith(("year", "twelve", "12")):
        return fy_label(fy_from_date(d))
    return None  # half year / nine months / generic period


def header_periods(line: str, context: str = "") -> list[Optional[str]]:
    """Ordered period labels for a table header line. `context` = the lines just above (for bare dates)."""
    found: list[tuple[int, int, Optional[str]]] = []

    def add(m, label):
        if any(s <= m.start() < e or s < m.end() <= e for s, e, _ in found):
            return
        found.append((m.start(), m.end(), label))

    for m in _ENDED_NUMERIC.finditer(line):
        try:
            add(m, _label_for(m.group(1), date(int(m.group(4)), int(m.group(3)), int(m.group(2)))))
        except ValueError:
            add(m, None)
    for m in _ENDED_TEXT.finditer(line):
        try:
            if m.group(2):
                d = date(int(m.group(4)), MONTHS[m.group(3)[:3].lower()], int(m.group(2)))
            else:
                d = date(int(m.group(7)), MONTHS[m.group(5)[:3].lower()], int(m.group(6)))
            add(m, _label_for(m.group(1), d))
        except (ValueError, KeyError):
            add(m, None)
    for rx, fn in ((_QTR, lambda m: quarter_label(int(m.group(1)[1]), _yr(m.group(2)))),
                   (_FY_SPAN, lambda m: fy_label(_yr(m.group(2)) if len(m.group(2)) == 4
                                                 else (int(m.group(1)) // 100) * 100 + int(m.group(2)))),
                   (_FY_SHORT, lambda m: fy_label(_yr(m.group(1))))):
        for m in rx.finditer(line):
            try:
                add(m, fn(m))
            except Exception:
                continue
    # two-digit fiscal spans: "Q1 26-27" -> Q1FY2027, "FY 25-26" / "25-26" -> FY2026 (consecutive years only)
    for m in _QTR_SHORT_SPAN.finditer(line):
        a, b = int(m.group(2)), int(m.group(3))
        if b == (a + 1) % 100:
            add(m, quarter_label(int(m.group(1)), 2000 + b))
    for m in _SHORT_SPAN.finditer(line):
        a, b = int(m.group(1)), int(m.group(2))
        if b == (a + 1) % 100 and not _BARE_DATE.search(line[max(0, m.start() - 3):m.end() + 5]):
            add(m, fy_label(2000 + b))
    # growth / change columns hold percentages, not periods: keep their position
    for m in _GROWTH_COL.finditer(line):
        add(m, None)
    # month-year tokens ("Mar 2025", "Jun-25"): March = fiscal year end unless the header also has other
    # quarter-end months (then it is a quarterly table and March = Q4).
    mon = [m for m in _MON_YEAR.finditer(line)]
    quarterly = any(MONTHS[m.group(1)[:3].lower()] in (6, 9, 12) for m in mon)
    # an annual table can end with one interim column ("Mar 2015 ... Mar 2026 Sep 2026": the latest half-year
    # balance sheet). Consecutive March years with at most one other month is still an annual table.
    mar_years = [_yr(m.group(2)) for m in mon if MONTHS[m.group(1)[:3].lower()] == 3]
    others = [m for m in mon if MONTHS[m.group(1)[:3].lower()] != 3]
    if quarterly and len(mar_years) >= 3 and len(others) <= 1 and \
            all(b - a == 1 for a, b in zip(mar_years, mar_years[1:])):
        quarterly = False
    for m in mon:
        mo, yr = MONTHS[m.group(1)[:3].lower()], _yr(m.group(2))
        d = date(yr, mo, 28)
        if mo == 3 and not quarterly:
            add(m, fy_label(fy_from_date(d)))
        elif mo in (3, 6, 9, 12):
            add(m, quarter_label(quarter_from_month(mo), fy_from_date(d)))
    # bare dates ("31.03.2026"): use the cue in the header block; ambiguous -> None
    cues = (context + " " + line).lower()
    has_q = bool(re.search(r"quarter|three\s+months|3\s+months", cues))
    has_y = bool(re.search(r"year[\s-]+end(ed)?|twelve\s+months|12\s+months|as\s+(at|on|of)|balance\s+sheet", cues))
    for m in _BARE_DATE.finditer(line):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if d.month not in (3, 6, 9, 12):
            add(m, None)
        elif has_q and not has_y:
            add(m, quarter_label(quarter_from_month(d.month), fy_from_date(d)))
        elif has_y and not has_q and d.month == 3:
            add(m, fy_label(fy_from_date(d)))
        elif d.month != 3:
            add(m, quarter_label(quarter_from_month(d.month), fy_from_date(d)))
        else:
            add(m, None)
    found.sort()
    labels = [p for _, _, p in found]
    # the same label twice in one header means quarter/year columns could not be told apart
    dup = {p for p in labels if p and labels.count(p) > 1}
    return [None if p in dup else p for p in labels]
