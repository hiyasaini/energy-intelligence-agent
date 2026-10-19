"""Hidden Risk: combines independent warning signals into a composite view.

A composite risk is raised only when warnings come from at least two different modules/evidence families,
so a single weak signal is never amplified into a headline.
"""
from __future__ import annotations

from ..metrics import metric_label
from .base import AnalysisContext, ModuleResult, Signal, fmt, latest_two

KEY, NAME = "hidden_risk", "Hidden Risk"
NEGATIVE_EVENTS = {"delay": 0.5, "curtailment": 0.45, "rating": 0.0}  # rating handled by direction words


def run(ctx: AnalysisContext, upstream: list[Signal]) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    components: list[tuple[str, str, float, list[str], list[str]]] = []  # (family, label, weight, facts, calcs)

    for s in upstream:
        if s.direction == "risk" and not s.insufficient and ":corr:" not in s.key:  # associations are not warnings
            components.append((s.module, s.title, s.severity, s.supporting_fact_ids, s.calc_ids))

    # receivable days trend
    rec, rev = ctx.series("receivables_cr"), ctx.series("revenue_cr")
    common = [p for p in rec.periods if rev.get(p)]
    days = []
    for p in common[-3:]:
        d = calc.ratio(f"Receivable days {p}", rec.get(p), rev.get(p), unit="days", scale=365,
                       formula="trade_receivables / revenue × 365")
        days.append(d)
        res.rows.append({"indicator": "Receivable days", "period": p, "value": fmt(d.result, "days", 0)})
    if len(days) >= 2 and days[-1].result and days[-2].result and days[-1].result > days[-2].result * 1.2:
        components.append(("working_capital", f"Receivable days up from {days[-2].result:.0f} to {days[-1].result:.0f}",
                           0.5, days[-1].input_fact_ids + days[-2].input_fact_ids, [days[-1].id, days[-2].id]))
        res.signals.append(Signal(
            key=f"{KEY}:receivables", module=KEY, title="Receivable days rising sharply",
            statement=f"Receivable days rose from {days[-2].result:.0f} ({days[-2].period}) to "
                      f"{days[-1].result:.0f} ({days[-1].period}), which can indicate slower collections from buyers.",
            direction="risk", severity=0.55, supporting_fact_ids=days[-1].input_fact_ids + days[-2].input_fact_ids,
            calc_ids=[days[-1].id, days[-2].id],
            limitations=["Year-end receivables are a single snapshot; seasonal billing can distort them.",
                         "Unbilled revenue or regulatory assets may be classified differently across years."],
            falsification="Weakened if collections improve in the next quarter or dues are cleared under a payment scheme.",
            counter_checks=["receivables_falling"],
            counter_queries=[f"{co} DISCOM dues payment", f"{co} late payment surcharge scheme receivables"]))
    elif not common:
        res.missing.append("receivables with matching revenue")

    # disclosed negative events
    for e in ctx.events(["delay", "curtailment"]):
        components.append(("disclosures", f"Disclosed {e.event_category}: {e.passage[:90]}…",
                           NEGATIVE_EVENTS[e.event_category], [e.id], []))
    downgrades = [e for e in ctx.events(["rating"]) if "downgrad" in e.passage.lower() or "negative" in e.passage.lower()]
    for e in downgrades:
        components.append(("disclosures", f"Rating pressure: {e.passage[:90]}…", 0.6, [e.id], []))

    # data contradictions are themselves a risk to the analysis
    conflicts = sum(len(ctx.series(m).conflicts) for m in
                    ["revenue_cr", "ebitda_cr", "gross_debt_cr", "installed_capacity_mw", "generation_mu", "pat_cr"])
    if conflicts:
        res.notes.append(f"{conflicts} metric/period combinations have conflicting values across sources "
                         "(see Contradiction Lab).")

    for fam, label, w, f, c in components:
        res.rows.append({"indicator": label, "family": fam, "weight": round(w, 2)})

    families = {c[0] for c in components}
    if len(families) >= 2:
        total = sum(c[2] for c in components)
        score = calc._rec(name="Composite risk score", formula="sum of component severities (each 0–1)",
                          input_fact_ids=sorted({i for c in components for i in c[3]}),
                          input_calc_ids=sorted({i for c in components for i in c[4]}),
                          inputs={c[1][:60]: round(c[2], 2) for c in components}, result=total, unit="score",
                          notes=f"{len(components)} components from {len(families)} independent families.")
        res.signals.append(Signal(
            key=f"{KEY}:composite", module=KEY,
            title=f"{len(components)} warning signals co-occur across {len(families)} areas",
            statement="Independent warnings appear together: " + "; ".join(c[1] for c in components[:5]) +
                      ". Co-occurrence raises the importance of each; it does not show they share a cause.",
            direction="risk", severity=min(0.95, 0.3 + 0.12 * len(components)),
            supporting_fact_ids=score.input_fact_ids, calc_ids=[score.id] + score.input_calc_ids,
            limitations=["Composite weights are heuristic and equal across families.",
                         "Components inherit the evidence quality of their source signals."],
            falsification="Weakened if two or more component signals are rejected or weakened on verification.",
            counter_checks=["components_hold"],
            counter_queries=[f"{co} credit rating rationale", f"{co} management commentary outlook"],
            params={"component_keys": [s.key for s in upstream if s.direction == "risk" and not s.insufficient
                                       and ":corr:" not in s.key]}))
    res.calcs = calc.records
    res.status = "ok" if components else ("partial" if days else "insufficient_data")
    res.summary = (f"{len(components)} warning component(s) across {len(families)} area(s)." if components else
                   "No warning signals with sufficient evidence were found." if days else
                   "Insufficient evidence: no warning indicators could be computed.")
    return res
