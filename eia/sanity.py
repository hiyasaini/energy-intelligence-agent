"""Physical plausibility of operating figures, judged against the company's own scale.

Prose in annual reports quotes many capacity and generation numbers that are not the company's operating level:
national totals, one project, a subsidiary, a ratio. Extraction rules catch most by wording; these checks catch
the rest by size. They are generic (business type and the company's own revenue), never company-specific, and a
point that fails is held out with the reason, never altered.
"""
from __future__ import annotations

from typing import Callable

from .calculations import Series

# no single Indian company comes near these (the largest generator is ~80 GW, ~450 BU a year)
ABS_MAX = {"installed_capacity_mw": 150_000, "renewable_capacity_mw": 150_000, "capacity_under_construction_mw": 150_000,
           "capacity_coal_mw": 150_000, "capacity_gas_mw": 50_000, "capacity_hydro_mw": 50_000,
           "capacity_nuclear_mw": 50_000, "capacity_solar_mw": 100_000, "capacity_wind_mw": 100_000,
           "generation_mu": 700_000, "coal_production_mt": 1_200, "coal_offtake_mt": 1_200,
           "crude_production_mt": 60, "oil_gas_production_mtoe": 100, "gas_production_bcm": 60,
           "refinery_throughput_mt": 150, "transmission_ckm": 400_000, "transformation_mva": 1_500_000}
# for a power producer: revenue per MW of installed capacity lies within roughly 0.4-25 ₹ cr a year
# (pure renewables at the low end, utilities with distribution at the high end); generation >= 3% PLF.
REV_PER_MW_MAX = 25.0
# revenue per unit generated: ₹2-8 per kWh for a generator (0.2-0.8 ₹ cr per MU), up to ~2 ₹ cr per MU for a utility
# that also distributes power; above 2.2 ₹ cr per MU, the generation figure covers one plant, not the company
REV_PER_MU_MAX = 2.2


CAPEX_MIN_SHARE = 0.005  # total capex below 0.5% of revenue is not plausible for an asset-heavy company


def apply(metric: str, s: Series, business: str, revenue: Callable[[str], float | None]) -> Series:
    cap = ABS_MAX.get(metric)
    for pt in list(s.points):
        reason = None
        if cap and pt.value > cap:
            reason = (f"{pt.value:,.0f} is above any Indian company's scale for this figure; most likely a national, "
                      "global or sector total quoted in the report.")
        elif business == "generator" and metric == "installed_capacity_mw":
            rev = revenue(pt.period)
            if rev and pt.value < rev / REV_PER_MW_MAX:
                reason = (f"{pt.value:,.0f} MW is too small for a power producer with ₹{rev:,.0f} cr revenue in "
                          f"{pt.period}; most likely one plant, project or subsidiary.")
        elif business == "generator" and metric == "generation_mu":
            rev = revenue(pt.period)
            if rev and pt.value < rev / REV_PER_MU_MAX:
                reason = (f"{pt.value:,.1f} MU is too small for a power producer with ₹{rev:,.0f} cr revenue in "
                          f"{pt.period}; most likely one plant, a saving or a ratio.")
        elif metric == "capex_cr" and business not in ("lender", "exchange"):
            rev = revenue(pt.period)
            if rev and rev >= 5000 and pt.value < rev * CAPEX_MIN_SHARE:
                reason = (f"₹{pt.value:,.0f} cr is under {CAPEX_MIN_SHARE:.1%} of ₹{rev:,.0f} cr revenue in {pt.period}; "
                          "most likely one project or a single line of the cash-flow statement, not total capex.")
        if reason:
            s.points = [p for p in s.points if p is not pt]
            s.excluded.append({"period": pt.period, "value": pt.value, "fact_id": pt.fact_id, "reason": reason})
            s.warnings.append(f"{metric} {pt.period}: {reason}")
    # a 4-fold step between consecutive years means the figures describe different assets; keep the most recent run
    pts = s.points
    cut = max((i for i in range(1, len(pts)) if pts[i - 1].value > 0 and
               not (1 / 4.0 <= pts[i].value / pts[i - 1].value <= 4.0)), default=0)
    for pt in pts[:cut]:
        reason = (f"{pt.value:,.1f} is inconsistent in scale with the later figures (a 4-fold step between years); "
                  "the later, more recent figures are used.")
        s.excluded.append({"period": pt.period, "value": pt.value, "fact_id": pt.fact_id, "reason": reason})
        s.warnings.append(f"{metric} {pt.period}: {reason}")
    s.points = pts[cut:]
    return s
