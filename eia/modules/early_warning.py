"""Early Warning: trend reversals, sharp decelerations and margin compression.

Quarterly comparisons use the same quarter of the prior year to avoid seasonal artefacts.
"""
from __future__ import annotations

from ..metrics import METRICS, metric_label
from .base import AnalysisContext, ModuleResult, Signal, fmt, latest_two, same_quarter_last_year

KEY, NAME = "early_warning", "Early Warning"
WATCH = ["revenue_cr", "ebitda_cr", "pat_cr", "generation_mu", "cfo_cr", "plf_cuf_pct",
         "gross_debt_cr", "finance_cost_cr", "receivables_cr"]


def _bad(metric: str, growth: float) -> bool:
    hib = METRICS[metric].higher_is_better
    if hib is None:
        return False
    return growth < 0 if hib else growth > 0


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    checked = 0
    for m in WATCH:
        s = ctx.series(m)
        if len(s) >= 3:
            pts = s.points
            g_prev = calc.growth(f"{metric_label(m)} YoY {pts[-2].period}", pts[-3], pts[-2])
            g_last = calc.growth(f"{metric_label(m)} YoY {pts[-1].period}", pts[-2], pts[-1])
            checked += 1
            if g_prev.result is not None and g_last.result is not None:
                res.rows.append({"metric": metric_label(m), "basis": "annual",
                                 "previous_growth": fmt(g_prev.result, "%"), "latest_growth": fmt(g_last.result, "%"),
                                 "period": pts[-1].period})
                reversal = (g_prev.result > 0) != (g_last.result > 0) and abs(g_last.result) >= 3
                decel = (g_prev.result > 10 and 0 <= g_last.result < g_prev.result * 0.4)
                if reversal or decel:
                    worse = _bad(m, g_last.result) or (decel and METRICS[m].higher_is_better)
                    kind = "reversal" if reversal else "sharp deceleration"
                    res.signals.append(Signal(
                        key=f"{KEY}:{kind.split()[0]}:{m}:annual", module=KEY,
                        title=f"{metric_label(m)}: {kind} in {pts[-1].period}",
                        statement=f"{metric_label(m)} growth moved from {g_prev.result:.1f}% ({pts[-2].period}) to "
                                  f"{g_last.result:.1f}% ({pts[-1].period}).",
                        direction="risk" if worse else "opportunity", severity=0.55 if worse else 0.35,
                        supporting_fact_ids=[pts[-3].fact_id, pts[-2].fact_id, pts[-1].fact_id],
                        calc_ids=[g_prev.id, g_last.id],
                        limitations=["Two growth rates are a short base; one-off items can cause a reversal."],
                        falsification="Weakened if the next quarter's same-quarter growth returns to the prior trend.",
                        counter_checks=["quarterly_rebound"],
                        counter_queries=[f"{co} quarterly results {metric_label(m)} latest quarter"],
                        params={"metric": m, "worse": worse}))
        q = ctx.series(m, "quarterly")
        if len(q) >= 2:
            last = q.points[-1]
            base = same_quarter_last_year(q, last)
            if base:
                g = calc.growth(f"{metric_label(m)} YoY {last.period}", base, last)
                checked += 1
                res.rows.append({"metric": metric_label(m), "basis": "same quarter last year",
                                 "previous_growth": "", "latest_growth": fmt(g.result, "%"), "period": last.period})
                if g.result is not None and _bad(m, g.result) and abs(g.result) >= 10:
                    res.signals.append(Signal(
                        key=f"{KEY}:quarter:{m}", module=KEY,
                        title=f"{metric_label(m)} moved {g.result:+.0f}% year on year in {last.period}",
                        statement=f"{metric_label(m)} was {fmt(last.value, last.unit)} in {last.period} vs "
                                  f"{fmt(base.value, base.unit)} a year earlier.",
                        direction="risk", severity=0.5, supporting_fact_ids=[base.fact_id, last.fact_id],
                        calc_ids=[g.id], limitations=["A single quarter can reflect weather, outages or timing."],
                        falsification="Weakened if the following quarter reverses the move.",
                        counter_checks=["quarterly_rebound"],
                        counter_queries=[f"{co} {last.period} results commentary"], params={"metric": m}))

    # EBITDA margin compression
    rev, eb = ctx.series("revenue_cr"), ctx.series("ebitda_cr")
    common = [p for p in rev.periods if eb.get(p)]
    if len(common) >= 2:
        m1 = calc.ratio(f"EBITDA margin {common[-2]}", eb.get(common[-2]), rev.get(common[-2]), "%", 100,
                        "ebitda / revenue × 100")
        m2 = calc.ratio(f"EBITDA margin {common[-1]}", eb.get(common[-1]), rev.get(common[-1]), "%", 100,
                        "ebitda / revenue × 100")
        if m1.result is not None and m2.result is not None:
            res.rows.append({"metric": "EBITDA margin", "basis": "annual", "previous_growth": fmt(m1.result, "%"),
                             "latest_growth": fmt(m2.result, "%"), "period": common[-1]})
            if m1.result - m2.result >= 3:
                res.signals.append(Signal(
                    key=f"{KEY}:margin", module=KEY,
                    title=f"EBITDA margin down {m1.result - m2.result:.1f} pp",
                    statement=f"EBITDA margin fell from {m1.result:.1f}% ({common[-2]}) to {m2.result:.1f}% ({common[-1]}).",
                    direction="risk", severity=0.5, supporting_fact_ids=m1.input_fact_ids + m2.input_fact_ids,
                    calc_ids=[m1.id, m2.id],
                    limitations=["Fuel cost pass-through inflates revenue and lowers margin without hurting profit.",
                                 "EBITDA definitions differ across sources (with/without other income)."],
                    falsification="Weakened if absolute EBITDA rose and the margin drop came from pass-through revenue.",
                    counter_checks=["ebitda_absolute_up"],
                    counter_queries=[f"{co} EBITDA margin fuel cost pass-through"]))
    res.calcs = calc.records
    res.status = "ok" if checked >= 3 else ("partial" if checked else "insufficient_data")
    res.summary = (f"{checked} trend check(s) run; {len(res.signals)} warning/reversal signal(s)."
                   if checked else "Insufficient evidence: trend checks need >=3 annual or comparable quarterly points.")
    if not checked:
        res.missing.append(">=3 annual points or same-quarter comparisons")
    return res
