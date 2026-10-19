"""Optional market data (share price + 1-year weekly history) for the dashboard header.

Source: Yahoo Finance's public chart endpoint (no key; unofficial, may change or rate-limit).
Turn off with EIA_MARKET_DATA=none. Failures return a MarketQuote with `error` set; nothing is estimated.
Market data is display-only context: it never feeds the findings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass
class MarketQuote:
    symbol: str
    price: Optional[float] = None
    change_pct: Optional[float] = None
    currency: str = "INR"
    as_of: str = ""
    dates: list[str] = field(default_factory=list)
    closes: list[float] = field(default_factory=list)
    source: str = "Yahoo Finance"
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    name: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.price is not None and not self.error


def enabled() -> bool:
    return os.getenv("EIA_MARKET_DATA", "yahoo").lower() not in ("none", "off", "false", "0")


def interval_is_daily(res: dict) -> bool:
    g = (res.get("meta") or {}).get("dataGranularity")
    return g in (None, "1d")


def parse_chart(symbol: str, data: dict) -> MarketQuote:
    q = MarketQuote(symbol)
    try:
        res = data["chart"]["result"][0]
        meta = res["meta"]
        q.price = float(meta["regularMarketPrice"])
        q.currency = meta.get("currency", "INR")
        q.high_52w = meta.get("fiftyTwoWeekHigh")
        q.low_52w = meta.get("fiftyTwoWeekLow")
        q.name = meta.get("longName") or meta.get("shortName") or ""
        ts = res.get("timestamp") or []
        closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        by_day: dict[str, float] = {}  # one close per calendar day; Yahoo often repeats the live bar
        for t_, c in zip(ts, closes):
            if c is not None:
                by_day[datetime.fromtimestamp(t_, tz=timezone.utc).strftime("%Y-%m-%d")] = float(c)
        q.dates = sorted(by_day)
        q.closes = [by_day[d] for d in q.dates]
        # day change: price vs the close of the last trading day BEFORE the latest quote's day
        t = meta.get("regularMarketTime")
        today = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d") if t else (q.dates[-1] if q.dates else "")
        prior = [d for d in q.dates if d < today]
        prev = meta.get("previousClose") if not prior else by_day[prior[-1]]
        if prev and interval_is_daily(res):
            q.change_pct = (q.price - float(prev)) / float(prev) * 100
        elif meta.get("previousClose"):
            q.change_pct = (q.price - float(meta["previousClose"])) / float(meta["previousClose"]) * 100
        t = meta.get("regularMarketTime")
        q.as_of = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%d %b %Y") if t else ""
    except (KeyError, IndexError, TypeError, ValueError) as e:
        return MarketQuote(symbol, error=f"unexpected response ({type(e).__name__})")
    return q


RANGES = {"5D": ("5d", "1d"), "1M": ("1mo", "1d"), "3M": ("3mo", "1d"), "6M": ("6mo", "1d"), "1Y": ("1y", "1wk"), "5Y": ("5y", "1mo")}
NIFTY50 = "^NSEI"


def fetch_chart(yahoo_symbol: str, period: str = "1Y", timeout: int = 8) -> MarketQuote:
    if not enabled():
        return MarketQuote(yahoo_symbol, error="market data turned off (EIA_MARKET_DATA=none)")
    rng, interval = RANGES.get(period, RANGES["1Y"])
    try:
        r = requests.get(CHART_URL.format(symbol=requests.utils.quote(yahoo_symbol)),
                         params={"range": rng, "interval": interval}, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"})
        if r.status_code >= 400:
            return MarketQuote(yahoo_symbol, error=f"HTTP {r.status_code}")
        return parse_chart(yahoo_symbol, r.json())
    except Exception as e:  # network blocked, timeout, bad JSON
        return MarketQuote(yahoo_symbol, error=f"{type(e).__name__}")


def fetch_quote(nse_symbol: str, timeout: int = 8, period: str = "1Y") -> MarketQuote:
    if not nse_symbol:
        return MarketQuote("", error="no NSE symbol")
    return fetch_chart(f"{nse_symbol.upper()}.NS", period, timeout)


def relative_performance(stock: MarketQuote, index: MarketQuote) -> dict:
    """Both series rebased to 0% at the first common date. Pure arithmetic on the fetched closes."""
    a = dict(zip(stock.dates, stock.closes))
    b = dict(zip(index.dates, index.closes))
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return {"dates": [], "stock": [], "index": []}
    a0, b0 = a[common[0]], b[common[0]]
    return {"dates": common, "stock": [(a[d] / a0 - 1) * 100 for d in common],
            "index": [(b[d] / b0 - 1) * 100 for d in common]}
