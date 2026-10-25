"""Canonical metric registry and unit normalisation.

Everything here is sector-generic (Indian power, renewables, oil & gas and coal reporting conventions).
Company-specific label aliases can be added through data/metric_aliases.json without code changes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# --- dimensions & units -----------------------------------------------------------------

CANONICAL_UNIT = {
    "power": "MW",
    "energy": "MU",        # million units = GWh
    "money": "INR_cr",     # Indian rupees, crore
    "percent": "%",
    "ratio": "x",
    "count": "count",
    "intensity": "tCO2/MWh",
    "mass": "Mt",          # million tonnes (coal, crude, refinery throughput)
    "oil_eq": "Mtoe",      # million tonnes of oil equivalent
    "gas_vol": "BCM",      # billion cubic metres
    "length": "ckm",       # circuit kilometres of transmission line
    "apparent_power": "MVA",
}

# unit token (lower-case, normalised) -> (dimension, multiplier to canonical)
UNIT_TABLE: dict[str, tuple[str, float]] = {
    # power
    "mw": ("power", 1.0), "mwp": ("power", 1.0), "mwac": ("power", 1.0), "mwdc": ("power", 1.0),
    "gw": ("power", 1000.0), "gwp": ("power", 1000.0), "gwac": ("power", 1000.0),
    "kw": ("power", 0.001), "kwp": ("power", 0.001),
    "megawatt": ("power", 1.0), "megawatts": ("power", 1.0),
    "gigawatt": ("power", 1000.0), "gigawatts": ("power", 1000.0),
    # energy
    "mu": ("energy", 1.0), "mus": ("energy", 1.0), "million units": ("energy", 1.0),
    "gwh": ("energy", 1.0), "bu": ("energy", 1000.0), "billion units": ("energy", 1000.0),
    "twh": ("energy", 1000.0), "mwh": ("energy", 0.001), "kwh": ("energy", 1e-6),
    # money (INR)
    "crore": ("money", 1.0), "crores": ("money", 1.0), "cr": ("money", 1.0), "cr.": ("money", 1.0),
    "lakh crore": ("money", 1e5), "lakh crores": ("money", 1e5), "lac crore": ("money", 1e5),
    "thousand crore": ("money", 1000.0),
    "lakh": ("money", 0.01), "lakhs": ("money", 0.01), "lac": ("money", 0.01), "lacs": ("money", 0.01),
    "million": ("money", 0.1), "mn": ("money", 0.1), "mln": ("money", 0.1),
    "billion": ("money", 100.0), "bn": ("money", 100.0),
    # percent / ratio
    "%": ("percent", 1.0), "percent": ("percent", 1.0), "per cent": ("percent", 1.0), "pct": ("percent", 1.0),
    "x": ("ratio", 1.0), "times": ("ratio", 1.0),
    # emission intensity (tCO2/MWh == kgCO2/kWh)
    "million tonnes": ("mass", 1.0), "million tonne": ("mass", 1.0), "million metric tonnes": ("mass", 1.0),
    "mmt": ("mass", 1.0), "mt": ("mass", 1.0), "mtpa": ("mass", 1.0), "mmtpa": ("mass", 1.0),
    "lakh tonnes": ("mass", 0.1), "billion tonnes": ("mass", 1000.0), "bt": ("mass", 1000.0),
    "mmtoe": ("oil_eq", 1.0), "mtoe": ("oil_eq", 1.0), "million tonnes of oil equivalent": ("oil_eq", 1.0),
    "bcm": ("gas_vol", 1.0), "billion cubic metres": ("gas_vol", 1.0), "billion cubic meters": ("gas_vol", 1.0),
    "mmscm": ("gas_vol", 0.001),
    "ckm": ("length", 1.0), "circuit km": ("length", 1.0), "circuit kilometres": ("length", 1.0),
    "circuit kilometers": ("length", 1.0),
    "mva": ("apparent_power", 1.0), "gva": ("apparent_power", 1000.0),
    "tco2/mwh": ("intensity", 1.0), "tco2e/mwh": ("intensity", 1.0), "tonnesco2/mwh": ("intensity", 1.0),
    "kgco2/kwh": ("intensity", 1.0), "kgco2e/kwh": ("intensity", 1.0), "kg/kwh": ("intensity", 1.0),
    "gco2/kwh": ("intensity", 0.001), "gco2e/kwh": ("intensity", 0.001),
}

FOREIGN_CURRENCY = re.compile(r"(US\$|USD|\$|EUR|€|£|GBP)\s?", re.I)


def normalise_unit_token(raw: str) -> str:
    t = (raw or "").strip().lower()
    t = t.replace("₹", "").replace("rs.", "").replace("rs", "").replace("inr", "").strip()
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t


def unit_factor(raw_unit: str, dimension: str) -> Optional[tuple[float, str]]:
    """Return (multiplier, canonical_unit) if raw_unit belongs to `dimension`, else None."""
    if FOREIGN_CURRENCY.search(raw_unit or "") and dimension == "money":
        return None  # never silently convert foreign currency
    tok = normalise_unit_token(raw_unit)
    if not tok and dimension in ("percent", "ratio", "count"):
        return 1.0, CANONICAL_UNIT[dimension]
    hit = UNIT_TABLE.get(tok) or UNIT_TABLE.get(tok.replace(" ", "").replace("₂", "2"))
    if hit and hit[0] == dimension:
        return hit[1], CANONICAL_UNIT[dimension]
    return None


def parse_number(s: str) -> Optional[float]:
    """Parse Indian/Western formatted numbers: '1,23,456.7', '(1,234)' (negative), '-12.5'."""
    if s is None:
        return None
    t = str(s).strip()
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "").replace("₹", "").strip()
    if t.startswith(("-", "−", "–")):
        neg = True
        t = t[1:]
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


# --- metric registry --------------------------------------------------------------------

@dataclass
class MetricDef:
    key: str
    label: str
    dimension: str
    keywords: list[str]              # regex fragments, case-insensitive
    kind: str = "flow"               # flow (per period) | stock (point in time)
    higher_is_better: Optional[bool] = True
    module_hint: str = ""
    patterns: list[re.Pattern] = field(default_factory=list, repr=False)

    def compile(self) -> None:
        self.patterns = [re.compile(k, re.I) for k in self.keywords]


# Order matters: more specific definitions first (first match wins in the rule extractor).
_SRC = r"(?:\s+(?:based|fired|power|energy|PV))?(?:\s+(?:operational|operating|installed))?\s+(?:plants?|stations?|capacity|portfolio|assets)"
_SRC_ROW = r"^\s*{}\s*(?:\(\s*MWp?\s*\))?\s*:?\s*$"


def _source_metric(key: str, label: str, words: str) -> "MetricDef":
    return MetricDef(key, label, "power", [rf"\b(?:{words}){_SRC}", _SRC_ROW.format(f"(?:{words})"),
                                           rf"^\s*(?:{words})\s*:"], "stock", None, "green_growth")


# Capacity by energy source (operating). Matched before generic capacity so "solar capacity" is not
# read as total capacity. Pipeline / under-construction sentences are excluded in the extractor.
SOURCE_CAPACITY = {
    "capacity_coal_mw": ("Coal", r"coal|lignite"),
    "capacity_gas_mw": ("Gas", r"gas|natural\s+gas|LNG"),
    "capacity_hydro_mw": ("Hydro", r"hydro|hydroelectric|hydro[\s-]?power"),
    "capacity_nuclear_mw": ("Nuclear", r"nuclear"),
    "capacity_solar_mw": ("Solar", r"solar"),
    "capacity_wind_mw": ("Wind", r"wind"),
}

_METRICS: list[MetricDef] = [
    *[_source_metric(k, f"{lab} capacity", w) for k, (lab, w) in SOURCE_CAPACITY.items()],
    MetricDef("emission_intensity", "Emission intensity", "intensity",
              [r"emissions?\s+intensity", r"CO2e?\s+(emissions?\s+)?intensity", r"carbon\s+intensity",
               r"specific\s+(CO2\s+)?emissions?"], "flow", False, "green_growth"),
    # oil, gas, coal and transmission businesses (Track B beyond power generation)
    MetricDef("oil_gas_production_mtoe", "Oil & gas production", "oil_eq",
              [r"(oil\s+(and|&)\s+gas|O\s?\+\s?OEG|hydrocarbons?)\s+production", r"production\s+of\s+(oil\s+(and|&)\s+gas|hydrocarbons)",
               r"\bO\s?\+\s?OEG\b"], "flow", True, "green_growth"),
    MetricDef("crude_production_mt", "Crude oil production", "mass",
              [r"crude(\s+oil)?\s+production", r"production\s+of\s+crude(\s+oil)?", r"crude\s+oil\s+output"],
              "flow", True, "green_growth"),
    MetricDef("gas_production_bcm", "Natural gas production", "gas_vol",
              [r"(natural\s+)?gas\s+production", r"production\s+of\s+(natural\s+)?gas", r"gas\s+output"],
              "flow", True, "green_growth"),
    MetricDef("refinery_throughput_mt", "Refinery throughput", "mass",
              [r"(refinery|refining|crude)\s+throughput", r"crude\s+(oil\s+)?(processed|processing)", r"throughput\s+of"],
              "flow", True, "green_growth"),
    MetricDef("coal_offtake_mt", "Coal offtake", "mass",
              [r"(coal\s+)?off[\s-]?take", r"coal\s+dispatch(es)?", r"coal\s+supplies"], "flow", True, "green_growth"),
    MetricDef("coal_production_mt", "Coal production", "mass",
              [r"(raw\s+)?coal\s+production", r"production\s+of\s+(raw\s+)?coal", r"coal\s+output"],
              "flow", True, "green_growth"),
    MetricDef("transmission_ckm", "Transmission network", "length",
              [r"transmission\s+(lines?|network)", r"circuit\s+(km|kilomet)", r"line\s+length"], "stock", True, "green_growth"),
    MetricDef("transformation_mva", "Transformation capacity", "apparent_power",
              [r"transformation\s+capacity", r"sub[\s-]?stations?", r"transformation\s+capability"], "stock", True, "green_growth"),
    MetricDef("capacity_under_construction_mw", "Capacity under construction", "power",
              [r"under[\s-]*(construction|execution|implementation|development)", r"capacity\s+in\s+(the\s+)?pipeline",
               r"locked[\s-]*in\s+(portfolio|capacity)"], "stock", None, "promise_reality"),
    MetricDef("renewable_capacity_mw", "Renewable operating capacity", "power",
              [r"\b(renewable|RE|green|clean)\s+(energy\s+)?(operational\s+|operating\s+|installed\s+)?capacity",
               r"operational\s+(renewable|RE)\s+capacity"], "stock", True, "green_growth"),
    MetricDef("installed_capacity_mw", "Installed / operating capacity", "power",
              [r"installed\s+(generation\s+|generating\s+)?capacity", r"operat(ing|ional)\s+capacity",
               r"total\s+(generation\s+)?capacity", r"capacity\s+(stood|stands)\s+at",
               r"(cumulative\s+)?capacity\s+(energi[sz]ed|commissioned|operationali[sz]ed)",
               r"(energi[sz]ed|operational)\s+capacity"],
              "stock", True, "green_growth"),
    MetricDef("generation_mu", "Electricity generation", "energy",
              [r"(power|electricity|energy|gross|net)\s+generation", r"\bgenerat(ed|ion)\b", r"energy\s+sold",
               r"units\s+(generated|sold)"], "flow", True, "green_growth"),
    MetricDef("plf_cuf_pct", "PLF / CUF", "percent",
              [r"\bPLF\b", r"plant\s+load\s+factor", r"\bCUF\b", r"capacity\s+utili[sz]ation\s+factor"],
              "flow", True, "green_growth"),
    MetricDef("revenue_cr", "Revenue from operations", "money",
              [r"revenue\s+from\s+operations", r"\b(total\s+|operating\s+|consolidated\s+)?revenues?\b",
               r"\bturnover\b", r"^\s*(net\s+)?sales\b"], "flow", True, "green_growth"),
    MetricDef("total_income_cr", "Total income", "money", [r"total\s+income"], "flow", True, "capital_cash"),
    MetricDef("ebitda_cr", "EBITDA", "money", [r"\bEBITDA\b", r"\bEBIDTA\b", r"\bPBDIT\b", r"operating\s+profit"],
              "flow", True, "capital_cash"),
    MetricDef("pat_cr", "Profit after tax", "money",
              [r"profit\s+after\s+tax", r"\bPAT\b", r"net\s+profit", r"profit\s+for\s+the\s+(year|period|quarter)"],
              "flow", True, "capital_cash"),
    MetricDef("capex_cr", "Capital expenditure", "money",
              [r"\bcapex\b", r"capital\s+expenditure", r"purchase\s+of\s+property,?\s+plant"], "flow", None, "capital_cash"),
    MetricDef("net_debt_cr", "Net debt", "money", [r"net\s+debt", r"net\s+borrowings"], "stock", False, "capital_cash"),
    MetricDef("borrowings_noncurrent_cr", "Non-current borrowings", "money", [r"non[\s-]*current\s+borrowings", r"borrowings,?\s*\(?non[\s-]*current"],
              "stock", False, "capital_cash"),
    MetricDef("borrowings_current_cr", "Current borrowings", "money", [r"^\s*current\s+borrowings",
              r"short[\s-]*term\s+borrowings", r"^\s*borrowings,?\s*\(?current"], "stock", False, "capital_cash"),
    MetricDef("gross_debt_cr", "Gross debt / borrowings", "money",
              [r"gross\s+debt", r"total\s+(debt|borrowings)", r"\bborrowings?\b", r"\bdebt\b"], "stock", False, "capital_cash"),
    MetricDef("cash_cr", "Cash & equivalents", "money",
              [r"cash\s+(and|&)\s+(cash\s+equivalents|bank)", r"cash\s+balance", r"liquidity\s+of"], "stock", True, "capital_cash"),
    MetricDef("finance_cost_cr", "Finance costs", "money",
              [r"finance\s+costs?", r"interest\s+(expense|cost)s?",
               r"^\s*interest(\s+and\s+finance\s+charges?)?\s*\+?\s*$"], "flow", False, "capital_cash"),
    MetricDef("cfo_cr", "Cash flow from operations", "money",
              [r"cash\s+(flow\s+)?(generated\s+)?from\s+operat", r"net\s+cash\s+(generated\s+)?(from|by)\s+operating",
               r"operating\s+cash\s+flow", r"cash\s+flows?\s+(generated\s+)?from[\s/()]*(used\s+in[\s)]*)?operat"],
              "flow", True, "capital_cash"),
    MetricDef("equity_cr", "Net worth / total equity", "money",
              [r"net\s+worth", r"total\s+equity", r"shareholders['’]?\s+(funds|equity)"], "stock", True, "capital_cash"),
    MetricDef("receivables_cr", "Trade receivables", "money",
              [r"trade\s+receivables", r"\breceivables\b", r"\bdues\s+from\s+discoms?"], "stock", False, "hidden_risk"),
    MetricDef("order_book_cr", "Order book", "money", [r"order\s+book", r"order\s+backlog"], "stock", True, "green_growth"),
]

METRICS: dict[str, MetricDef] = {}
for _m in _METRICS:
    _m.compile()
    METRICS[_m.key] = _m

# Target metrics share the dimension of their base metric.
TARGET_BASE = {
    "capacity_target_mw": "installed_capacity_mw",
    "renewable_target_mw": "renewable_capacity_mw",
    "capex_target_cr": "capex_cr",
    "generation_target_mu": "generation_mu",
    "revenue_target_cr": "revenue_cr",
    "coal_target_mt": "coal_production_mt",
    "oil_gas_target_mtoe": "oil_gas_production_mtoe",
    "refining_target_mt": "refinery_throughput_mt",
    "transmission_target_ckm": "transmission_ckm",
    "transformation_target_mva": "transformation_mva",
}
TARGET_LABELS = {
    "capacity_target_mw": "Capacity target",
    "renewable_target_mw": "Renewable capacity target",
    "capex_target_cr": "Capex plan / guidance",
    "generation_target_mu": "Generation target",
    "revenue_target_cr": "Revenue target",
    "coal_target_mt": "Coal production target",
    "oil_gas_target_mtoe": "Oil & gas production target",
    "refining_target_mt": "Refining target",
    "transmission_target_ckm": "Transmission network target",
    "transformation_target_mva": "Transformation capacity target",
}


def metric_label(key: str) -> str:
    if key in METRICS:
        return METRICS[key].label
    return TARGET_LABELS.get(key, key.replace("_", " "))


def metric_dimension(key: str) -> Optional[str]:
    if key in METRICS:
        return METRICS[key].dimension
    if key in TARGET_BASE:
        return METRICS[TARGET_BASE[key]].dimension
    return None


def load_alias_overrides(path: Optional[Path] = None) -> dict[str, list[str]]:
    """Optional, configurable label aliases: {"metric_key": ["regex", ...]}. Never contains findings."""
    p = path or (ROOT / "data" / "metric_aliases.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for k, regs in data.items():
        if k in METRICS and isinstance(regs, list):
            out[k] = [str(r) for r in regs]
    return out


def apply_alias_overrides() -> None:
    for key, regs in load_alias_overrides().items():
        m = METRICS[key]
        for r in regs:
            if r not in m.keywords:
                m.keywords.append(r)
                m.patterns.append(re.compile(r, re.I))


apply_alias_overrides()
