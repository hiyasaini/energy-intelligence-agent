"""Green Growth: capacity, generation and revenue trends, and whether they move together."""
from __future__ import annotations

from ..metrics import metric_label
from .base import AnalysisContext, ModuleResult, Signal, fmt, latest_two

KEY, NAME = "green_growth", "Green Growth"
METRICS_USED = ["installed_capacity_mw", "renewable_capacity_mw", "generation_mu", "revenue_cr", "plf_cuf_pct"]
GAP_PP = 10.0   # growth gap (percentage points) treated as a meaningful divergence


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    cagr = {}
    for m in METRICS_USED:
        s = ctx.series(m)
        res.relationships += ctx.conflict_relationships(s, KEY)
        if len(s) == 0:
            res.missing.append(metric_label(m))
            continue
        res.series[m] = s
        prev, cur = latest_two(s)
        g = calc.growth(f"{metric_label(m)} YoY", prev, cur)
        c = calc.cagr(f"{metric_label(m)} CAGR", s)
        cagr[m] = c
        res.rows.append({"metric": metric_label(m), "latest": fmt(cur.value, cur.unit) if cur else "n/a",
                         "period": cur.period if cur else "", "yoy": fmt(g.result, "%") if g.result is not None else "n/a",
                         "cagr": fmt(c.result, "%") if c.result is not None else "n/a",
                         "points": len(s), "conflicts": len(s.conflicts)})
        res.notes += s.warnings

    cap_key = "renewable_capacity_mw" if cagr.get("renewable_capacity_mw") and \
        cagr["renewable_capacity_mw"].result is not None else "installed_capacity_mw"
    cap = cagr.get(cap_key)

    # renewable share
    ren, inst = ctx.series("renewable_capacity_mw"), ctx.series("installed_capacity_mw")
    common = [p for p in ren.periods if inst.get(p)]
    if common:
        p = common[-1]
        share = calc.ratio("Renewable share of capacity", ren.get(p), inst.get(p), unit="%", scale=100,
                           formula="renewable_capacity / installed_capacity × 100")
        res.rows.append({"metric": "Renewable share of capacity", "latest": fmt(share.result, "%"), "period": p})

    # implied utilisation: generation / (capacity × 8760h)
    gen = ctx.series("generation_mu")
    cap_series = ctx.series(cap_key)
    for p in [x for x in gen.periods if cap_series.get(x)][-3:]:
        g, c = gen.get(p), cap_series.get(p)
        u = calc._rec(name=f"Implied utilisation {p}", formula="generation_MU × 1000 / (capacity_MW × 8760) × 100",
                      input_fact_ids=[g.fact_id, c.fact_id], inputs={"generation_MU": g.value, "capacity_MW": c.value},
                      result=g.value * 1000 / (c.value * 8760) * 100 if c.value else None, unit="%", period=p,
                      notes="Uses period-end capacity, which understates utilisation when capacity was added during the year.")
        res.rows.append({"metric": f"Implied utilisation ({metric_label(cap_key)})", "latest": fmt(u.result, "%"), "period": p})

    def divergence(other: str, label: str, risk_title: str):
        o = cagr.get(other)
        if not cap or not o or cap.result is None or o.result is None:
            return
        gap = cap.result - o.result
        if gap >= GAP_PP:
            res.signals.append(Signal(
                key=f"{KEY}:lag:{other}", module=KEY, title=risk_title,
                statement=f"{metric_label(cap_key)} grew at {cap.result:.1f}% a year while {label} grew at "
                          f"{o.result:.1f}% ({cap.period} vs {o.period}). New capacity is not yet showing up "
                          f"proportionally in {label}.",
                direction="risk", severity=min(0.85, 0.35 + gap / 60),
                supporting_fact_ids=cap.input_fact_ids + o.input_fact_ids, calc_ids=[cap.id, o.id],
                limitations=["Capacity commissioned late in the year contributes little to that year's output.",
                             "Periods compared may not be identical; check the calculation inputs.",
                             "Lower resource years (wind/solar/hydro) depress output without any execution issue."],
                falsification=f"Weakened if utilisation (PLF/CUF) is stable or if most new capacity was commissioned "
                              f"in the last quarter; rejected if the gap closes in the next annual period.",
                counter_checks=["late_year_commissioning", "stable_utilisation"],
                counter_queries=[f"{co} PLF CUF {label}", f"{co} commissioned capacity quarter",
                                 f"{co} curtailment transmission constraint"],
                params={"gap_pp": gap}))
        elif o.result >= 10 and cap.result >= 10 and abs(gap) < GAP_PP:
            res.signals.append(Signal(
                key=f"{KEY}:aligned:{other}", module=KEY,
                title=f"Capacity and {label} growing together",
                statement=f"{metric_label(cap_key)} CAGR {cap.result:.1f}% and {label} CAGR {o.result:.1f}% are "
                          "within 10 percentage points, consistent with new assets contributing output.",
                direction="opportunity", severity=0.35, supporting_fact_ids=cap.input_fact_ids + o.input_fact_ids,
                calc_ids=[cap.id, o.id], limitations=["Co-movement does not show which assets drive revenue."],
                falsification="Weakened if a later period shows the growth rates diverging by more than 10pp.",
                counter_checks=["delay_events"], counter_queries=[f"{co} project delay"]))

    divergence("generation_mu", "generation", "Generation growth lags capacity growth")
    divergence("revenue_cr", "revenue", "Revenue growth lags capacity growth")

    res.calcs = calc.records
    have = len(METRICS_USED) - len(res.missing)
    res.status = "insufficient_data" if have == 0 else ("ok" if have >= 3 else "partial")
    res.summary = (f"{have}/{len(METRICS_USED)} growth metrics found." if have else
                   "Insufficient evidence: no capacity, generation or revenue series found.")
    return res
