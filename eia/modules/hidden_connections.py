"""Hidden Connections: links between events and metrics where evidence supports a relationship.

Two link types, both labelled 'inferred' and never described as causal:
  * metric co-movement: Pearson r of YoY changes over >=4 overlapping periods, |r| >= 0.8;
  * event -> metric consistency: a dated commissioning / financing event followed, in the next reported period,
    by a change in the related metric of comparable size.
"""
from __future__ import annotations

from ..calculations import MIN_CORR_PERIODS
from ..metrics import metric_label
from ..periods import fy_from_date, fy_label, period_sort_key
from ..schema import Relationship, RelLabel
from .base import AnalysisContext, ModuleResult, Signal, fmt

KEY, NAME = "hidden_connections", "Hidden Connections"
PAIRS = [  # (a, b, lag, expected sign, plain-language relation)
    ("installed_capacity_mw", "generation_mu", 0, 1, "capacity and generation"),
    ("renewable_capacity_mw", "generation_mu", 0, 1, "renewable capacity and generation"),
    ("installed_capacity_mw", "revenue_cr", 0, 1, "capacity and revenue"),
    ("capex_cr", "finance_cost_cr", 1, 1, "capex and next-year finance costs"),
    ("gross_debt_cr", "finance_cost_cr", 0, 1, "debt and finance costs"),
    ("generation_mu", "revenue_cr", 0, 1, "generation and revenue"),
    ("receivables_cr", "cfo_cr", 0, -1, "receivables and operating cash flow"),
]
R_MIN = 0.8


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    tested = 0
    for a, b, lag, sign, rel in PAIRS:
        for periodicity in ("annual", "quarterly"):
            sa, sb = ctx.series(a, periodicity), ctx.series(b, periodicity)
            if len(sa) < MIN_CORR_PERIODS or len(sb) < MIN_CORR_PERIODS:
                continue
            c = calc.correlation(f"Co-movement: {rel} ({periodicity})", sa, sb, lag)
            tested += 1
            res.rows.append({"link": rel, "periodicity": periodicity, "lag": lag,
                             "r": f"{c.result:.2f}" if c.result is not None else c.status.replace("_", " "),
                             "periods": c.inputs.get("periods", "")})
            if c.result is None:
                continue
            if abs(c.result) >= R_MIN:
                consistent = (c.result > 0) == (sign > 0)
                res.relationships.append(Relationship(
                    run_id=ctx.run_id, src_type="metric", src_id=a, dst_type="metric", dst_id=b,
                    relation="linked_to", label=RelLabel.inferred,
                    note=f"r={c.result:.2f} over {c.inputs.get('n_changes')} changes; correlation, not causation"))
                res.signals.append(Signal(
                    key=f"{KEY}:corr:{a}:{b}:{periodicity}", module=KEY,
                    title=f"{rel.capitalize()} move {'together' if c.result > 0 else 'in opposite directions'}"
                          f"{'' if consistent else ' (unexpected direction)'}",
                    statement=f"Year-on-year changes in {metric_label(a)} and {metric_label(b)}"
                              f"{' (one period later)' if lag else ''} have r = {c.result:.2f} across "
                              f"{c.inputs.get('n_changes')} changes. This is a statistical association only.",
                    direction="neutral" if consistent else "risk", severity=0.3 if consistent else 0.5,
                    supporting_fact_ids=c.input_fact_ids, calc_ids=[c.id],
                    limitations=["Few observations; a single outlier year can drive r.",
                                 "Shared growth trends inflate correlation; this does not identify a mechanism."],
                    falsification="Rejected if adding further periods drops |r| below 0.8.",
                    max_strength="weak" if (c.inputs.get("n_changes") or 0) < 8 else "moderate",
                    counter_checks=["more_periods"], counter_queries=[f"{co} {metric_label(b)} quarterly"]))

    # event -> metric consistency (commissioning -> capacity)
    cap_key = "renewable_capacity_mw" if ctx.has("renewable_capacity_mw") else "installed_capacity_mw"
    cap = ctx.series(cap_key)
    for e in ctx.events(["commissioning"]):
        if e.value is None or not e.period_end:
            continue
        from datetime import date
        try:
            d = date.fromisoformat(e.period_end)
        except ValueError:
            continue
        fy = fy_from_date(d)
        cur, prev = cap.get(fy_label(fy)), cap.get(fy_label(fy - 1))
        res.relationships.append(Relationship(
            run_id=ctx.run_id, src_type="fact", src_id=e.id, dst_type="metric", dst_id=cap_key,
            relation="concerns", label=RelLabel.observed, note="Commissioning disclosure concerns this metric"))
        if not cur or not prev:
            continue
        add = calc.change(f"Capacity added in {fy_label(fy)}", prev, cur)
        if add.result is None:
            continue
        ok = add.result >= e.value * 0.8
        res.relationships.append(Relationship(
            run_id=ctx.run_id, src_type="fact", src_id=e.id, dst_type="calc", dst_id=add.id,
            relation="linked_to", label=RelLabel.inferred if ok else RelLabel.contradictory,
            note=("Reported capacity addition is large enough to include this commissioning"
                  if ok else "Reported capacity addition is smaller than this commissioning")))
        res.rows.append({"link": f"Commissioning {fmt(e.value, 'MW')} ({e.period_end})",
                         "periodicity": "event", "lag": 0,
                         "r": "consistent" if ok else "inconsistent",
                         "periods": f"{fy_label(fy)} addition {fmt(add.result, 'MW')}"})
        if not ok:
            res.signals.append(Signal(
                key=f"{KEY}:event_gap:{e.id}", module=KEY,
                title="Announced commissioning not visible in reported capacity",
                statement=f"A commissioning of {fmt(e.value, 'MW')} is disclosed ({e.period_end}), but reported "
                          f"{metric_label(cap_key).lower()} rose only {fmt(add.result, 'MW')} in {fy_label(fy)}.",
                direction="risk", severity=0.55, supporting_fact_ids=[e.id, cur.fact_id, prev.fact_id],
                calc_ids=[add.id],
                limitations=["The commissioned asset may sit in a JV/parent outside reported scope.",
                             "Retirements or divestments in the same year offset additions."],
                falsification="Rejected if the asset is shown to be outside the reporting scope or offset by retirements.",
                counter_checks=["scope_or_retirement"],
                counter_queries=[f"{co} joint venture capacity", f"{co} divestment retirement capacity"]))

    res.calcs = calc.records
    n_events = len(ctx.events(["commissioning"]))
    res.status = "ok" if tested else ("partial" if n_events else "insufficient_data")
    res.summary = (f"{tested} metric pair(s) tested; {sum(1 for s in res.signals if s.key.startswith(KEY + ':corr'))} "
                   f"strong co-movement(s); {len(ctx.events(['commissioning']))} commissioning event(s) checked."
                   if tested or ctx.events(['commissioning']) else
                   f"Insufficient evidence: correlation needs >={MIN_CORR_PERIODS} overlapping periods for a metric pair.")
    if not tested:
        res.missing.append(f">={MIN_CORR_PERIODS} overlapping periods for any metric pair")
    return res
