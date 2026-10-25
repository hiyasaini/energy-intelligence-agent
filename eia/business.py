"""Business model of a company, from its registry segment. Decides which figures mean what for it.

The same words mean different things in different businesses: "12 GW capacity" is generation capacity for a
power producer but factory output for a solar-module maker; "debt / EBITDA 8x" is a warning for a generator but
normal for a lender. Rules here are by business type, never by company name.
"""
from __future__ import annotations

import re

POWER_ASSETS = {"installed_capacity_mw", "renewable_capacity_mw", "capacity_under_construction_mw", "generation_mu",
                "plf_cuf_pct", "capacity_coal_mw", "capacity_gas_mw", "capacity_hydro_mw", "capacity_nuclear_mw",
                "capacity_solar_mw", "capacity_wind_mw", "capacity_target_mw", "renewable_target_mw",
                "generation_target_mu", "emission_intensity"}
LENDER_BALANCE = {"gross_debt_cr", "net_debt_cr", "finance_cost_cr"}

TYPES = [  # first match wins
    ("lender", r"financ|lend|nbfc|bank"),
    ("exchange", r"exchange|trading platform"),
    ("manufacturer", r"manufactur|equipment|epc|o&m|glass|module|turbine|cell"),
    ("coal", r"coal|lignite"),
    ("transmission", r"transmission|grid"),
    ("oil_gas", r"oil|gas|refin|petro|lng|upstream|downstream"),
    ("generator", r"generation|ipp|utility|utilit|hydro|thermal|renewable|solar|wind|power"),
    ("conglomerate", r"conglomerate"),
]
# metrics that, for this business, would be read under a meaning the company does not have
EXCLUDE = {
    "lender": POWER_ASSETS,          # a lender's "capacity" figures are its borrowers' projects
    "exchange": POWER_ASSETS,        # volumes traded are not generation
    "manufacturer": POWER_ASSETS,    # "GW" is manufacturing or order-book capacity, not generation assets
}
NOTE = {
    "lender": "Lender: capacity and generation figures in its reports describe financed projects, so they are not "
              "analysed as the company's own assets; leverage is its business model, not a warning.",
    "exchange": "Power exchange: traded volumes are not generation, so capacity and generation are not analysed.",
    "manufacturer": "Manufacturer / EPC / services: GW figures are manufacturing, order-book or serviced capacity, not "
                    "generation assets, so they are not analysed as installed capacity or generation.",
}


def business_type(segment: str) -> str:
    seg = (segment or "").lower()
    if seg.startswith("non-energy"):
        return "lender" if re.search(r"financ|bank|insur|nbfc", seg) else "other"
    if "conglomerate" in seg:
        return "conglomerate"
    for name, rx in TYPES:
        if re.search(rx, seg):
            return name
    return "other"


def excluded_metrics(segment: str) -> set[str]:
    return EXCLUDE.get(business_type(segment), set())


def is_lender(segment: str) -> bool:
    return business_type(segment) == "lender"
