"""Key-free primary sources for listed Indian companies, used in every live run.

* NSE annual reports        https://www.nseindia.com/api/annual-reports?index=equities&symbol=SYM
* NSE corporate filings     https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=SYM
  (results, investor presentations, press releases, commissioning / financing disclosures)
* Screener consolidated     https://www.screener.in/company/SYM/consolidated/  (multi-year tables, aggregator tier)

NSE's API needs a browser-like session (cookies from the home page). Everything here fails soft: an error
is returned to the agent, which logs it and carries on with whatever else it found.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import requests

from .search import SearchResult

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36")
NSE = "https://www.nseindia.com"
ANNOUNCE_KEEP = re.compile(r"financial\s+result|results?\b|investor\s+presentation|analysts?\s*/?\s*institutional|"
                           r"press\s+release|commission|commercial\s+operation|outcome\s+of\s+board|credit\s+rating|"
                           r"acquisition|award|letter\s+of\s+award|bond|QIP|fund\s+rais", re.I)
URL_RX = re.compile(r"https?://[^\s\"']+\.(?:pdf|zip|html?|xml)\b", re.I)


@dataclass
class DirectFindings:
    results: list[SearchResult] = field(default_factory=list)   # documents to fetch
    digest: Optional[tuple[str, str, str]] = None               # (title, url, text) of announcement headlines
    errors: list[str] = field(default_factory=list)


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _first(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "-"):
            return str(v)
    return ""


def _url_in(d: dict) -> str:
    for v in d.values():
        if isinstance(v, str):
            m = URL_RX.search(v)
            if m:
                return m.group(0)
    return ""


def parse_annual_reports(data: Any, symbol: str, limit: int = 2) -> list[SearchResult]:
    rows = []
    for d in _walk(data):
        url = _url_in(d)
        if not url:
            continue
        frm, to = _first(d, "fromYr", "fromYear", "from_year"), _first(d, "toYr", "toYear", "to_year")
        year = int(to) if to.isdigit() else (int(frm) + 1 if frm.isdigit() else 0)
        title = f"{_first(d, 'companyName', 'company') or symbol} annual report {frm}-{to}".strip()
        rows.append((year, SearchResult(title, url, "NSE annual report filing", f"{year}-09-30" if year else None)))
    rows.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, r in rows:
        if r.url not in seen:
            seen.add(r.url)
            out.append(r)
    return out[:limit]


def _ann_date(d: dict) -> Optional[str]:
    raw = _first(d, "an_dt", "sort_date", "dt", "date", "exchdisstime").strip()
    for text, fmt in ((raw, "%d-%b-%Y %H:%M:%S"), (raw, "%Y-%m-%d %H:%M:%S"), (raw.split(" ")[0], "%d-%b-%Y"),
                      (raw.split(" ")[0], "%Y-%m-%d"), (raw.split(" ")[0], "%d-%m-%Y")):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_announcements(data: Any, symbol: str, limit: int = 5) -> tuple[list[SearchResult], list[tuple[str, str, str]]]:
    """Returns (documents worth fetching, all headline rows (date, subject, detail))."""
    keep, heads = [], []
    for d in _walk(data):
        subject = _first(d, "desc", "subject", "sm_name_desc", "category")
        detail = _first(d, "attchmntText", "details", "sm_desc")
        if not (subject or detail):
            continue
        date = _ann_date(d)
        url = _url_in(d)
        heads.append((date or "", subject, detail))
        if url and ANNOUNCE_KEEP.search(f"{subject} {detail}"):
            keep.append((date or "", SearchResult(f"{symbol} filing: {subject[:80]}".strip(), url, detail[:300], date)))
    keep.sort(key=lambda x: x[0], reverse=True)
    heads.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in keep[:limit]], heads[:40]


def announcement_digest(symbol: str, heads: list[tuple[str, str, str]]) -> str:
    """Plain-text page of exchange announcements; dated lines let the extractor place events on the timeline."""
    lines = [f"{symbol} corporate announcements filed with NSE (exchange filing headlines)"]
    for date, subject, detail in heads:
        try:
            d = datetime.fromisoformat(date).strftime("%d %B %Y") if date else ""
        except ValueError:
            d = date
        text = re.sub(r"\s+", " ", f"{subject}: {detail}").strip(" :")
        lines.append(f"On {d}, {text}" if d else text)
    return "\n\n".join(lines)


class DirectSources:
    name = "direct"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": BROWSER_UA, "Accept": "application/json,text/html,*/*",
                                     "Accept-Language": "en-IN,en;q=0.9", "Referer": NSE + "/"})
        self._warm = False

    def _nse_json(self, path: str) -> Any:
        if not self._warm:
            self.session.get(NSE, timeout=self.timeout)
            self._warm = True
        r = self.session.get(NSE + path, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")
        return r.json()

    def discover(self, symbol: str) -> DirectFindings:
        out = DirectFindings()
        if not symbol:
            out.errors.append("no NSE symbol, so exchange filings cannot be looked up")
            return out
        sym = symbol.upper()
        try:
            out.results += parse_annual_reports(self._nse_json(f"/api/annual-reports?index=equities&symbol={sym}"), sym)
        except Exception as e:
            out.errors.append(f"NSE annual reports: {type(e).__name__}: {str(e)[:120]}")
        try:
            docs, heads = parse_announcements(
                self._nse_json(f"/api/corporate-announcements?index=equities&symbol={sym}"), sym)
            out.results += docs
            if heads:
                out.digest = (f"{sym} NSE corporate announcements",
                              f"{NSE}/get-quotes/equity?symbol={sym}", announcement_digest(sym, heads))
        except Exception as e:
            out.errors.append(f"NSE announcements: {type(e).__name__}: {str(e)[:120]}")
        out.results.append(SearchResult(f"{sym} consolidated financials (Screener)",
                                        f"https://www.screener.in/company/{sym}/consolidated/",
                                        "multi-year financial tables"))
        return out
