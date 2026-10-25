"""Green Growth: capacity, generation and revenue trends, and whether they move together."""
from __future__ import annotations

from ..calculations import Series
from ..metrics import metric_label
from .base import AnalysisContext, ModuleResult, Signal, fmt, latest_two

KEY, NAME = "green_growth", "Green Growth"
METRICS_USED = ["installed_capacity_mw", "renewable_capacity_mw", "generation_mu", "revenue_cr", "plf_cuf_pct"]
GAP_PP = 10.0   # growth gap (percentage points) treated as a meaningful divergence
# physical volumes that revenue should broadly follow (first ones are closest to "what was sold")
VOLUME_METRICS = ["generation_mu", "coal_offtake_mt", "coal_production_mt", "oil_gas_production_mtoe",
                  "crude_production_mt", "gas_production_bcm", "refinery_throughput_mt"]
NETWORK_METRICS = ["transmission_ckm", "transformation_mva"]
VOLUME_GAP_PP = 6.0  # revenue vs volume CAGR gap that indicates price- (or volume-) led growth


def _common_window(a: Series, b: Series) -> tuple[Series, Series]:
    """Both series restricted to the periods they share, so their growth rates cover the same years."""
    common = [p for p in a.periods if b.get(p)]
    return (Series(a.metric, a.unit, [a.get(p) for p in common]),
            Series(b.metric, b.unit, [b.get(p) for p in common]))


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    from ..business import NOTE, business_type
    if business_type(ctx.company.segment) in NOTE:
        res.notes.append(NOTE[business_type(ctx.company.segment)])
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
    valid = [p for p in common if inst.get(p).value > 0 and ren.get(p).value <= inst.get(p).value]
    if common and not valid:
        res.notes.append("Renewable capacity exceeds installed capacity in every shared year (the two figures likely "
                         "cover different entities, e.g. group vs company); renewable share not computed.")
    if valid:
        p = valid[-1]
        share = calc.ratio("Renewable share of capacity", ren.get(p), inst.get(p), unit="%", scale=100,
                           formula="renewable_capacity / installed_capacity × 100")
        res.rows.append({"metric": "Renewable share of capacity", "latest": fmt(share.result, "%"), "period": p})

    # implied utilisation: generation / (capacity × 8760h); outside 3-100% the inputs cannot belong together
    gen_inconsistent = False
    gen = ctx.series("generation_mu")
    cap_series = ctx.series(cap_key)
    for p in [x for x in gen.periods if cap_series.get(x)][-3:]:
        g, c = gen.get(p), cap_series.get(p)
        u = calc._rec(name=f"Implied utilisation {p}", formula="generation_MU × 1000 / (capacity_MW × 8760) × 100",
                      input_fact_ids=[g.fact_id, c.fact_id], inputs={"generation_MU": g.value, "capacity_MW": c.value},
                      result=g.value * 1000 / (c.value * 8760) * 100 if c.value else None, unit="%", period=p,
                      notes="Uses period-end capacity, which understates utilisation when capacity was added during the year.")
        if u.result is not None and not (3 <= u.result <= 100):
            gen_inconsistent = True
            res.notes.append(f"Generation and capacity for {p} imply {u.result:,.0f}% utilisation, which is not physically "
                             "possible; the two figures cover different assets or units, so generation is not compared "
                             "with capacity.")
            continue
        res.rows.append({"metric": f"Implied utilisation ({metric_label(cap_key)})", "latest": fmt(u.result, "%"), "period": p})

    def divergence(other: str, label: str, risk_title: str):
        if not cap or cap.result is None or len(ctx.series(other)) < 2:
            return
        if other == "generation_mu" and gen_inconsistent:
            return
        # compare growth over the SAME years only
        c_s, o_s = _common_window(ctx.series(cap_key), ctx.series(other))
        if len(c_s) < 3:
            return
        cap_c = calc.cagr(f"{metric_label(cap_key)} CAGR (years shared with {label})", c_s)
        o = calc.cagr(f"{metric_label(other)} CAGR (years shared with capacity)", o_s)
        if cap_c.result is None or o.result is None:
            return
        cap_local = cap_c
        gap = cap_local.result - o.result
        if gap >= GAP_PP:
            res.signals.append(Signal(
                key=f"{KEY}:lag:{other}", module=KEY, title=risk_title,
                statement=f"Over {cap_local.period}, {metric_label(cap_key).lower()} grew {cap_local.result:.1f}% a year "
                          f"while {label} grew {o.result:.1f}%. New capacity is not yet showing up proportionally in "
                          f"{label}.",
                direction="risk", severity=min(0.85, 0.35 + gap / 60),
                supporting_fact_ids=cap_local.input_fact_ids + o.input_fact_ids, calc_ids=[cap_local.id, o.id],
                limitations=["Capacity commissioned late in the year contributes little to that year's output.",
                             "Lower resource years (wind/solar/hydro) depress output without any execution issue."],
                falsification=f"Weakened if utilisation (PLF/CUF) is stable or if most new capacity was commissioned "
                              f"in the last quarter; rejected if the gap closes in the next annual period.",
                counter_checks=["late_year_commissioning", "stable_utilisation"],
                counter_queries=[f"{co} PLF CUF {label}", f"{co} commissioned capacity quarter",
                                 f"{co} curtailment transmission constraint"],
                params={"gap_pp": gap}))
        elif o.result >= 10 and cap_local.result >= 10 and abs(gap) < GAP_PP:
            res.signals.append(Signal(
                key=f"{KEY}:aligned:{other}", module=KEY,
                title=f"Capacity and {label} growing together",
                statement=f"{metric_label(cap_key)} CAGR {cap_local.result:.1f}% and {label} CAGR {o.result:.1f}% are "
                          "within 10 percentage points, consistent with new assets contributing output.",
                direction="opportunity", severity=0.35, supporting_fact_ids=cap_local.input_fact_ids + o.input_fact_ids,
                calc_ids=[cap_local.id, o.id], limitations=["Co-movement does not show which assets drive revenue."],
                falsification="Weakened if a later period shows the growth rates diverging by more than 10pp.",
                counter_checks=["delay_events"], counter_queries=[f"{co} project delay"]))

    divergence("generation_mu", "generation", "Generation growth lags capacity growth")
    divergence("revenue_cr", "revenue", "Revenue growth lags capacity growth")

    # ---- price-led vs volume-led growth (any physical volume the company reports) -----------------
    rev = ctx.series("revenue_cr")
    for vm in VOLUME_METRICS + NETWORK_METRICS:
        vs = ctx.series(vm)
        if len(vs) == 0:
            continue
        res.series[vm] = vs
        res.notes += vs.warnings
        vc = calc.cagr(f"{metric_label(vm)} CAGR", vs)
        prev, cur = latest_two(vs)
        res.rows.append({"metric": metric_label(vm), "latest": fmt(cur.value, cur.unit) if cur else "n/a",
                         "period": cur.period if cur else "",
                         "cagr": fmt(vc.result, "%") if vc.result is not None else "n/a", "points": len(vs)})
    vol_key = next((m for m in VOLUME_METRICS if len(_common_window(ctx.series(m), rev)[0]) >= 3), None)
    if vol_key:
        v_s, r_s = _common_window(ctx.series(vol_key), rev)
        vc = calc.cagr(f"{metric_label(vol_key)} CAGR (common years)", v_s)
        rc = calc.cagr("Revenue CAGR (common years)", r_s)
        if vc.result is not None and rc.result is not None:
            gap = rc.result - vc.result
            implied = calc._rec(
                name="Implied price / realisation growth", formula="(1 + revenue CAGR) / (1 + volume CAGR) - 1",
                input_fact_ids=vc.input_fact_ids + rc.input_fact_ids, input_calc_ids=[vc.id, rc.id],
                inputs={"revenue_cagr_pct": rc.result, "volume_cagr_pct": vc.result},
                result=((1 + rc.result / 100) / (1 + vc.result / 100) - 1) * 100, unit="%", period=vc.period,
                notes="Revenue also reflects product mix, other income lines and non-volume businesses.")
            res.rows.append({"metric": f"Implied price growth vs {metric_label(vol_key).lower()}",
                             "latest": fmt(implied.result, "%"), "period": vc.period})
            label = metric_label(vol_key).lower()
            common = dict(supporting_fact_ids=vc.input_fact_ids + rc.input_fact_ids, calc_ids=[vc.id, rc.id, implied.id],
                          counter_checks=["sector_wide", "more_periods"],
                          counter_queries=[f"{co} realisation price per unit", f"{co} tariff price revision",
                                           f"{co} sales volume growth"])
            if gap >= VOLUME_GAP_PP:
                res.signals.append(Signal(
                    key=f"{KEY}:price_led:{vol_key}", module=KEY, title="Revenue growth is price-led, not volume-led",
                    statement=f"Over {vc.period}, revenue grew {rc.result:.1f}% a year while {label} grew "
                              f"{vc.result:.1f}%, implying about {implied.result:.1f}% a year from price, tariff or mix "
                              f"rather than volume.",
                    direction="risk", severity=min(0.8, 0.35 + gap / 40),
                    limitations=["Revenue includes segments and other operating income that are not tied to this volume.",
                                 "Regulated tariffs can rise for reasons that are sustainable (pass-through of costs)."],
                    falsification=f"Rejected if {label} growth catches up with revenue growth in the next annual period, "
                                  "or if sector peers show the same gap (a sector-wide price cycle).",
                    params={"gap_pp": gap}, **common))
            elif gap <= -VOLUME_GAP_PP:
                res.signals.append(Signal(
                    key=f"{KEY}:realisation_down:{vol_key}", module=KEY, title="Volumes are growing faster than revenue",
                    statement=f"Over {vc.period}, {label} grew {vc.result:.1f}% a year but revenue only "
                              f"{rc.result:.1f}%, implying falling realisations of about {abs(implied.result):.1f}% a year.",
                    direction="risk", severity=min(0.75, 0.3 + abs(gap) / 40),
                    limitations=["A shift towards lower-priced products or customers lowers realisations without "
                                 "any weakness in demand."],
                    falsification="Rejected if realisations stabilise in the next annual period or peers show the "
                                  "same pattern.",
                    params={"gap_pp": gap}, **common))

    res.calcs = calc.records
    extra = [m for m in VOLUME_METRICS + NETWORK_METRICS if m != "generation_mu" and len(ctx.series(m))]
    if extra:  # an oil, gas, coal or transmission business: power-only metrics are not "missing"
        res.missing = [m for m in res.missing if m in (metric_label("revenue_cr"),)]
    have = len(METRICS_USED) - len([m for m in METRICS_USED if metric_label(m) in res.missing]) + len(extra)
    if extra:
        have = len([m for m in METRICS_USED if len(ctx.series(m))]) + len(extra)
    res.status = "insufficient_data" if have == 0 else ("ok" if have >= 3 else "partial")
    res.summary = (f"{have} growth and volume series found." if have else
                   "Insufficient evidence: no capacity, production, generation or revenue series found.")
    return res
