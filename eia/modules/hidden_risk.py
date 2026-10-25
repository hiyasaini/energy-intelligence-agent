"""Hidden Risk: combines independent warning signals into a composite view.

A composite risk is raised only when warnings come from at least two different modules/evidence families,
so a single weak signal is never amplified into a headline.
"""
from __future__ import annotations

from ..metrics import metric_label
from .base import AnalysisContext, ModuleResult, Signal, fmt, latest_two

KEY, NAME = "hidden_risk", "Hidden Risk"
NEGATIVE_EVENTS = {"delay": 0.5, "curtailment": 0.45, "rating": 0.0}  # rating handled by direction words


def _subject(label: str) -> str:
    import re
    m = re.match(r"\s*(.+?)(?::| moved | disclosed| up from | is | growing| down | \()", label)
    sub = (m.group(1) if m else label).strip()
    return {"Delays": "project delays", "Curtailments": "curtailments", "Rating pressure": "rating pressure"}.get(sub, sub)


def _composite_title(components: list, n_families: int) -> str:
    """Name what moves together, so the headline says something on its own."""
    subs = list(dict.fromkeys(_subject(c[1]) for c in sorted(components, key=lambda c: -c[2])))[:3]
    subs = [x if i == 0 or (len(x) > 1 and x[1].isupper()) else x[0].lower() + x[1:] for i, x in enumerate(subs)]
    if len(subs) >= 2:
        named = ", ".join(subs[:-1]) + " and " + subs[-1]
        return f"{named[0].upper() + named[1:]} flash warnings together ({len(components)} signals, {n_families} area{'s' if n_families != 1 else ''})"
    return f"{len(components)} warning signals co-occur across {n_families} areas"


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
    mixed = [p for p in common if "unknown" not in (rec.get(p).scope, rev.get(p).scope)
             and rec.get(p).scope != rev.get(p).scope]
    if mixed:
        res.notes.append(f"Receivable days not computed for {', '.join(mixed)}: receivables and revenue come from "
                         "different reporting scopes (consolidated vs standalone).")
    for p in [x for x in common if x not in mixed][-3:]:
        d = calc.ratio(f"Receivable days {p}", rec.get(p), rev.get(p), unit="days", scale=365,
                       formula="trade_receivables / revenue × 365")
        if d.result is not None and not (1 <= d.result <= 730):
            res.notes.append(f"Receivable days of {d.result:,.0f} in {p} is outside any plausible range; "
                             "the inputs likely cover different entities or units, so it is not used.")
            continue
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

    # disclosed negative events: ONE component per kind, however many sentences mention it (a long annual
    # report can mention "delay" dozens of times; that is one warning, not dozens)
    def _distinct(events):
        seen, out = set(), []
        for e in events:
            k = " ".join(e.passage.lower().split())[:160]
            if k not in seen:
                seen.add(k)
                out.append(e)
        return out
    for cat in ("delay", "curtailment"):
        evs = _distinct(ctx.events([cat]))
        if len(evs) >= 2:   # a single mention is anecdote, not a pattern
            components.append(("disclosures", f"{cat.capitalize()}s disclosed ({len(evs)} distinct mention(s))", NEGATIVE_EVENTS[cat],
                               [e.id for e in evs[:5]], []))
    downgrades = _distinct([e for e in ctx.events(["rating"])
                            if "downgrad" in e.passage.lower() or "negative" in e.passage.lower()])
    if downgrades:
        components.append(("disclosures", f"Rating pressure ({len(downgrades)} mention(s))", 0.6, [e.id for e in downgrades[:5]], []))

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
            title=_composite_title(components, len(families)),
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
