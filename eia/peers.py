"""Peer comparison: is a finding specific to the company, or something the whole sector is going through?

Peers come from the identity registry (data/companies.csv): listed companies in the same line of business,
chosen by segment keywords, never by company name. For each peer the same key-free financial tables used for
the company (Screener consolidated page) are read with the same extraction rules, and the same deterministic
ratios are computed. A counter-check then compares the company with the peer median:

  * company in line with peers  -> "opposes" (weight 0.35): the pattern looks sector-wide, not company-specific;
  * company clearly worse       -> "supports" (weight 0.3): the company is an outlier among its peers.

Weight 0.35 alone never rejects or weakens a finding (that needs 0.4); it becomes the stated counterargument.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

from .calculations import Series, build_series
from .periods import is_annual, period_sort_key
from .schema import Company, Fact

SCREENER = "https://www.screener.in/company/{sym}/consolidated/"
FAMILIES = [  # first match wins; order matters ("power sector finance" is a lender, "renewable generation" is power)
    ("finance", r"financ|lend"),
    ("exchange", r"exchange"),
    ("equipment", r"manufactur|equipment|epc|o&m|glass"),
    ("coal", r"coal|lignite|mining"),
    ("transmission", r"transmission|grid"),
    ("oil_gas", r"oil|gas|refin|petro|conglomerate|upstream|downstream|lng"),
    ("power", r"generation|renewable|solar|wind|hydro|thermal|power|utilit|distribution|discom"),
]


def family(segment: str) -> str:
    if (segment or "").strip().lower().startswith("non-energy"):
        return ""          # outside Track B: no energy peers
    for name, rx in FAMILIES:
        if re.search(rx, segment or "", re.I):
            return name
    return ""


GENERIC_WORDS = {"power", "oil", "gas", "indian", "india", "national", "energy", "green", "the", "hindustan", "bharat",
                 "coal", "grid", "renewable", "renewables", "solar", "wind", "petroleum", "electric"}


def _group_word(name: str) -> str:
    """First word of the name when it identifies a business group (not a generic word like Power), else ''."""
    w = (name or "").split()[0].lower() if name else ""
    return "" if w in GENERIC_WORDS else w


def choose_peers(company: Company, registry: list[Company], n: int = 3) -> list[Company]:
    """Up to n listed companies in the same line of business, excluding the company and its group members."""
    fam = family(company.segment)
    if not fam:
        return []
    own_sym, own_group = company.nse.upper(), _group_word(company.name)
    out = []
    for c in registry:
        if not c.nse or c.nse.upper() == own_sym or (own_group and _group_word(c.name) == own_group):
            continue
        if family(c.segment) == fam:
            out.append(c)
        if len(out) >= n:
            break
    return out


# ---- comparable figures (all computed from the same extraction rules) -----------------------------

METRIC_NAMES = {
    "revenue_cagr": "Revenue growth, % a year",
    "ebitda_cagr": "EBITDA growth, % a year",
    "debt_to_ebitda": "Debt / EBITDA, x",
    "coverage": "Interest coverage, x",
    "cfo_to_ebitda": "Cash conversion (CFO / EBITDA), x",
    "ebitda_margin": "EBITDA margin, %",
    "margin_change": "EBITDA margin change, pp",
    "debt_minus_ebitda_growth": "Debt growth minus EBITDA growth, pp",
    "fincost_minus_revenue_growth": "Finance-cost growth minus revenue growth, pp",
}


def _annual(s: Series) -> list:
    return [p for p in s.points if is_annual(p.period)]


def _cagr(s: Series, years: int = 3) -> Optional[float]:
    pts = _annual(s)[-(years + 1):]
    if len(pts) < 2 or pts[0].value <= 0 or pts[-1].value <= 0:
        return None
    n = period_sort_key(pts[-1].period)[0] - period_sort_key(pts[0].period)[0]
    return ((pts[-1].value / pts[0].value) ** (1 / n) - 1) * 100 if n > 0 else None


def _latest_ratio(a: Series, b: Series) -> Optional[float]:
    common = [p for p in a.periods if b.get(p) and is_annual(p)]
    if not common:
        return None
    p = common[-1]
    den = b.get(p).value
    return a.get(p).value / den if den else None


def profile(facts: list[Fact], tiers: Optional[dict] = None) -> dict[str, Optional[float]]:
    S = {m: build_series(facts, m, tiers or {}) for m in
         ("revenue_cr", "ebitda_cr", "gross_debt_cr", "finance_cost_cr", "cfo_cr")}
    out: dict[str, Optional[float]] = {
        "revenue_cagr": _cagr(S["revenue_cr"]), "ebitda_cagr": _cagr(S["ebitda_cr"]),
        "debt_to_ebitda": _latest_ratio(S["gross_debt_cr"], S["ebitda_cr"]),
        "coverage": _latest_ratio(S["ebitda_cr"], S["finance_cost_cr"]),
        "cfo_to_ebitda": _latest_ratio(S["cfo_cr"], S["ebitda_cr"]),
    }
    m = _latest_ratio(S["ebitda_cr"], S["revenue_cr"])
    out["ebitda_margin"] = m * 100 if m is not None else None
    common = [p for p in S["ebitda_cr"].periods if S["revenue_cr"].get(p) and is_annual(p)]
    if len(common) >= 3 and S["revenue_cr"].get(common[-3]).value and S["revenue_cr"].get(common[-1]).value:
        m_now = S["ebitda_cr"].get(common[-1]).value / S["revenue_cr"].get(common[-1]).value * 100
        m_then = S["ebitda_cr"].get(common[-3]).value / S["revenue_cr"].get(common[-3]).value * 100
        out["margin_change"] = m_now - m_then
    else:
        out["margin_change"] = None
    dg, eg = _cagr(S["gross_debt_cr"]), out["ebitda_cagr"]
    out["debt_minus_ebitda_growth"] = dg - eg if dg is not None and eg is not None else None
    fg, rg = _cagr(S["finance_cost_cr"]), out["revenue_cagr"]
    out["fincost_minus_revenue_growth"] = fg - rg if fg is not None and rg is not None else None
    out["_period"] = S["revenue_cr"].periods[-1] if len(S["revenue_cr"]) else None
    return out


@dataclass
class PeerProfile:
    symbol: str
    name: str
    url: str
    metrics: dict = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "name": self.name, "url": self.url, "metrics": self.metrics, "error": self.error}


def collect(company: Company, registry: list[Company], fetch: Callable, parse: Callable, extract: Callable,
            n: int = 3) -> list[PeerProfile]:
    """fetch(url)->FetchResult, parse(bytes, content_type, url)->Document, extract(doc, symbol)->list[Fact].
    A failing peer is recorded with its error; it never stops the run."""
    out = []
    for p in choose_peers(company, registry, n):
        url = SCREENER.format(sym=p.nse.upper())
        prof = PeerProfile(p.nse.upper(), p.name, url)
        try:
            fr = fetch(url)
            if not fr.ok:
                prof.error = fr.error or "fetch failed"
            else:
                facts = extract(parse(fr.content, fr.content_type, url), p.nse.upper())
                prof.metrics = profile(facts)
                if all(v is None for k, v in prof.metrics.items() if not k.startswith("_")):
                    prof.error = "no comparable figures found"
        except Exception as e:
            prof.error = f"{type(e).__name__}: {str(e)[:120]}"
        out.append(prof)
    return out


# ---- the counter-check ------------------------------------------------------------------------------

# finding type -> (comparable figure, True if a higher value is worse, margin that counts as "in line")
COMPARE = {
    "capital_cash:leverage": ("debt_to_ebitda", True, 0.25),
    "capital_cash:coverage": ("coverage", False, 0.25),
    "capital_cash:conversion": ("cfo_to_ebitda", False, 0.2),
    "capital_cash:debt_outpaces_ebitda": ("debt_minus_ebitda_growth", True, 5.0),
    "capital_cash:finance_cost_outpaces_revenue": ("fincost_minus_revenue_growth", True, 5.0),
    "capital_cash:deleveraging": ("debt_minus_ebitda_growth", True, 5.0),
    "green_growth:price_led": ("revenue_cagr", True, 5.0),
    "green_growth:lag:revenue_cr": ("revenue_cagr", False, 5.0),
    "early_warning:margin": ("margin_change", False, 2.0),
}
RELATIVE = {"debt_to_ebitda", "coverage", "cfo_to_ebitda"}  # margins for these are relative, others absolute


def comparable(signal_key: str) -> Optional[tuple]:
    parts = signal_key.split(":")
    return COMPARE.get(":".join(parts[:3])) or COMPARE.get(":".join(parts[:2]))


def compare(signal_key: str, company_metrics: dict, peers: list[PeerProfile]) -> Optional[dict]:
    spec = comparable(signal_key)
    if not spec:
        return None
    key, higher_worse, margin = spec
    cv = company_metrics.get(key)
    vals = [(p, p.metrics.get(key)) for p in peers if p.metrics.get(key) is not None]
    if cv is None or len(vals) < 2:
        return None
    med = statistics.median(v for _, v in vals)
    band = abs(med) * margin if key in RELATIVE else margin
    diff = cv - med
    worse = diff > band if higher_worse else diff < -band
    detail = ", ".join(f"{p.name.split(' Ltd')[0]} {v:,.2f}" for p, v in vals)
    return {"metric": key, "label": METRIC_NAMES[key], "company": cv, "median": med, "peers": detail,
            "verdict": "outlier" if worse else "in_line", "peer_symbols": [p.symbol for p, _ in vals]}
