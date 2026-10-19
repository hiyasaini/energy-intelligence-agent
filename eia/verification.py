"""Hypothesis generation, counter-evidence checks and evidence grading.

Module Signals become Hypotheses (one per stable signal key, revised across rounds, never duplicated).
Each hypothesis is challenged by deterministic counter-checks that look for evidence AGAINST it in the
collected facts, and graded by the quality and diversity of its supporting evidence.

Status rules (deterministic, in priority order):
  insufficient_evidence  module flagged the signal as untestable, or no supporting facts
  rejected               a decisive counter-check (weight >= 0.8) found opposing evidence
  weakened               opposing evidence with combined weight >= 0.4
  unresolved             inputs contradict each other, rely on unverified facts, or evidence is weak
  proposed               counter-evidence search not yet run (only between rounds)
  supported              moderate/strong evidence and no material opposing evidence after searching
Causation is never asserted: statements and counterarguments say "consistent with", not "caused by".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .calculations import Point
from .metrics import metric_label
from .modules.base import AnalysisContext, Signal, latest_two, same_quarter_last_year
from .periods import period_sort_key
from .schema import (TIER_WEIGHT, Fact, FactStatus, Hypothesis, HypothesisStatus, Scope, SourceTier,
                     Strength, now_iso)


@dataclass
class CheckOutcome:
    check: str
    effect: str = "no_evidence"        # opposes | supports | neutral | no_evidence
    weight: float = 0.0                # how decisive the evidence is (0..1)
    fact_ids: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {"check": self.check, "effect": self.effect, "weight": round(self.weight, 2),
                "fact_ids": self.fact_ids, "note": self.note}


# ---------------------------------------------------------------------------------------------
# Counter-checks. Each looks for evidence that would weaken the signal. They only read facts and
# compute with plain Python; anything they cannot evaluate returns effect="no_evidence".
# ---------------------------------------------------------------------------------------------

def _latest(ctx: AnalysisContext, metric: str) -> Optional[Point]:
    return ctx.latest_point(metric)


def _latest_fy(ctx: AnalysisContext) -> Optional[int]:
    """Latest fiscal year with an annual reported figure (quarters of a later year do not count)."""
    from .periods import is_annual
    fys = [period_sort_key(f.period)[0] for f in ctx.facts
           if f.fact_type.value == "reported" and is_annual(f.period)]
    return max(fys) if fys else None


def _events_matching(ctx: AnalysisContext, cats: list[str], rx: Optional[str] = None) -> list[Fact]:
    ev = ctx.events(cats)
    if rx:
        r = re.compile(rx, re.I)
        ev = [e for e in ev if r.search(e.passage)]
    return ev


def chk_pipeline_covers_gap(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("pipeline_covers_gap")
    gap = s.params.get("gap")
    uc = _latest(ctx, "capacity_under_construction_mw")
    if gap is None or uc is None:
        o.note = "No disclosed capacity under construction found to compare with the remaining gap."
        return o
    cover = uc.value / gap if gap > 0 else 1.0
    o.fact_ids = [uc.fact_id]
    if cover >= 1.0:
        o.effect, o.weight = "opposes", 0.85
        o.note = (f"Capacity under construction ({uc.value:,.0f} MW, {uc.period}) covers the remaining gap of "
                  f"{gap:,.0f} MW ({cover:.0%}).")
    elif cover >= 0.5:
        o.effect, o.weight = "opposes", 0.45
        o.note = (f"Capacity under construction ({uc.value:,.0f} MW, {uc.period}) covers {cover:.0%} of the "
                  f"{gap:,.0f} MW gap — partial mitigation.")
    else:
        o.effect, o.weight = "supports", 0.3
        o.note = f"Capacity under construction ({uc.value:,.0f} MW) covers only {cover:.0%} of the {gap:,.0f} MW gap."
    return o


def chk_recent_commissioning(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("recent_commissioning")
    fy = _latest_fy(ctx)
    ev = [e for e in ctx.events(["commissioning"]) if e.period_end and fy and
          e.period_end >= f"{fy - 1}-04-01"]
    if not ev:
        o.note = "No dated commissioning disclosures in the latest fiscal year."
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = "opposes", 0.3
    total = sum(e.value or 0 for e in ev)
    o.note = (f"{len(ev)} commissioning disclosure(s) in FY{fy}" + (f" totalling {total:,.0f} MW" if total else "") +
              "; recent additions may explain the pattern (timing, not necessarily execution).")
    return o


def chk_late_year_commissioning(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("late_year_commissioning")
    fy = _latest_fy(ctx)
    if not fy:
        return o
    ev = [e for e in ctx.events(["commissioning"]) if e.period_end and
          f"{fy - 1}-10-01" <= e.period_end <= f"{fy}-03-31"]
    if not ev:
        o.note = f"No commissioning disclosures in the second half of FY{fy}."
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = "opposes", 0.4
    o.note = (f"{len(ev)} commissioning(s) dated in H2 FY{fy}; capacity added late in the year contributes "
              "little to that year's output or revenue.")
    return o


def chk_stable_utilisation(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("stable_utilisation")
    ser = ctx.series("plf_cuf_pct")
    prev, cur = latest_two(ser)
    if not prev or not cur:
        o.note = "PLF/CUF history not available."
        return o
    d = cur.value - prev.value
    o.fact_ids = [prev.fact_id, cur.fact_id]
    if abs(d) <= 2:
        o.effect, o.weight = "opposes", 0.35
        o.note = f"PLF/CUF stable ({prev.value:.1f}% → {cur.value:.1f}%), so existing assets are not underperforming."
    elif d < -2:
        o.effect, o.weight = "supports", 0.35
        o.note = f"PLF/CUF fell {abs(d):.1f} pp ({prev.period} → {cur.period}), consistent with weaker utilisation."
    else:
        o.effect, o.weight = "opposes", 0.4
        o.note = f"PLF/CUF rose {d:.1f} pp, which argues against an operating problem."
    return o


def chk_equity_raise(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("equity_raise")
    ev = _events_matching(ctx, ["financing"], r"QIP|qualified\s+institutional|rights\s+issue|equity|preferential|IPO|OFS")
    if not ev:
        o.note = "No equity raise disclosed in collected sources."
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = "opposes", 0.4
    o.note = f"{len(ev)} equity-raising disclosure(s) found; new equity reduces leverage pressure."
    return o


def chk_funding_secured(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("funding_secured")
    ev = ctx.events(["financing"])
    if not ev:
        o.note = "No financing tie-ups disclosed in collected sources."
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = "opposes", 0.3
    o.note = f"{len(ev)} financing disclosure(s) (loans, bonds or equity) found; part of the funding need may be tied up."
    return o


def chk_cash_buffer(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("cash_buffer")
    cash = _latest(ctx, "cash_cr")
    debt = _latest(ctx, "gross_debt_cr") or _latest(ctx, "net_debt_cr")
    if not cash or not debt or not debt.value:
        o.note = "Cash or debt balance not available."
        return o
    r = cash.value / debt.value
    o.fact_ids = [cash.fact_id, debt.fact_id]
    if r >= 0.2:
        o.effect, o.weight = "opposes", 0.3
        o.note = f"Cash is {r:.0%} of debt ({cash.period}), a meaningful liquidity buffer."
    else:
        o.effect, o.weight = "supports", 0.2
        o.note = f"Cash is only {r:.0%} of debt ({cash.period})."
    return o


def chk_refinancing(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("refinancing")
    ev = _events_matching(ctx, ["financing", "rating"], r"refinanc|upgrade|lower\s+(interest|cost)")
    if not ev:
        o.note = "No refinancing or rating upgrade disclosed."
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = "opposes", 0.35
    o.note = f"{len(ev)} refinancing / upgrade disclosure(s) could lower finance costs."
    return o


def chk_receivables_falling(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("receivables_falling")
    q = ctx.series("receivables_cr", "quarterly")
    a = ctx.series("receivables_cr")
    if not len(a):
        o.note = "Receivables not disclosed."
        return o
    last_a = a.points[-1]
    later = [p for p in q.points if period_sort_key(p.period) > period_sort_key(last_a.period)]
    if later:
        lq = later[-1]
        o.fact_ids = [last_a.fact_id, lq.fact_id]
        if lq.value < last_a.value * 0.9:
            o.effect, o.weight = "opposes", 0.45
            o.note = f"Receivables fell from {last_a.value:,.0f} ({last_a.period}) to {lq.value:,.0f} ({lq.period})."
        else:
            o.effect, o.weight = "supports", 0.25
            o.note = f"Receivables did not fall after {last_a.period} ({lq.value:,.0f} in {lq.period})."
        return o
    ev = _events_matching(ctx, ["financing", "announcement", "award", "ppa"], r"dues|LPS|late\s+payment")
    if ev:
        o.fact_ids = [e.id for e in ev]
        o.effect, o.weight = "neutral", 0.0
        o.note = "Disclosures mention dues / late-payment schemes; effect on balances not quantified."
        return o
    o.note = "No later receivables figure to test whether collections improved."
    return o


def chk_delay_events(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("delay_events")
    ev = ctx.events(["delay", "curtailment"])
    if not ev:
        o.note = "No delay or curtailment disclosures found."
        o.effect = "supports" if s.direction == "opportunity" else "no_evidence"
        o.weight = 0.15 if s.direction == "opportunity" else 0.0
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = ("opposes", 0.45) if s.direction == "opportunity" else ("supports", 0.3)
    o.note = f"{len(ev)} delay/curtailment disclosure(s) found."
    return o


def chk_pipeline_large(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("pipeline_large")
    uc = _latest(ctx, "capacity_under_construction_mw")
    op = _latest(ctx, "renewable_capacity_mw") or _latest(ctx, "installed_capacity_mw")
    if not uc or not op or not op.value:
        o.note = "Pipeline or operating capacity not available."
        return o
    r = uc.value / op.value
    o.fact_ids = [uc.fact_id, op.fact_id]
    if r >= 0.3:
        o.effect, o.weight = "opposes", 0.4
        o.note = (f"Capacity under construction is {r:.0%} of operating capacity; debt is likely funding assets "
                  "that have not yet started earning EBITDA.")
    else:
        o.effect, o.weight = "supports", 0.2
        o.note = f"Capacity under construction is only {r:.0%} of operating capacity."
    return o


def chk_quarterly_rebound(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("quarterly_rebound")
    m = s.params.get("metric")
    if not m:
        return o
    q = ctx.series(m, "quarterly")
    a = ctx.series(m)
    if len(q) < 2:
        o.note = f"No comparable quarterly {metric_label(m)} figures."
        return o
    last = q.points[-1]
    base = same_quarter_last_year(q, last)
    if not base or not base.value:
        o.note = "No same-quarter-last-year comparison available."
        return o
    g = (last.value - base.value) / abs(base.value) * 100
    o.fact_ids = [base.fact_id, last.fact_id]
    # if the signal is about the annual series, a later quarter moving the other way opposes it
    latest_annual = a.points[-1].period if len(a) else ""
    if s.key.endswith(":annual") and period_sort_key(last.period) <= period_sort_key(latest_annual):
        o.note = "Latest quarter is not later than the latest annual period."
        return o
    from .metrics import METRICS
    hib = METRICS[m].higher_is_better if m in METRICS else True
    good = (g > 0) if hib else (g < 0)
    if s.direction == "risk" and good and abs(g) >= 3:
        o.effect, o.weight = "opposes", 0.45
        o.note = f"{metric_label(m)} {last.period} moved {g:+.1f}% vs {base.period}, against the warning."
    elif s.direction == "risk" and not good and abs(g) >= 3:
        o.effect, o.weight = "supports", 0.3
        o.note = f"{metric_label(m)} {last.period} moved {g:+.1f}% vs {base.period}, consistent with the warning."
    else:
        o.effect = "neutral"
        o.note = f"{metric_label(m)} {last.period} moved {g:+.1f}% vs {base.period}."
    return o


def chk_ebitda_absolute_up(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("ebitda_absolute_up")
    prev, cur = latest_two(ctx.series("ebitda_cr"))
    if not prev or not cur:
        return o
    o.fact_ids = [prev.fact_id, cur.fact_id]
    if cur.value > prev.value:
        o.effect, o.weight = "opposes", 0.4
        o.note = f"Absolute EBITDA still rose ({prev.value:,.0f} → {cur.value:,.0f}); margin fall may be revenue mix/pass-through."
    else:
        o.effect, o.weight = "supports", 0.3
        o.note = f"Absolute EBITDA also fell ({prev.value:,.0f} → {cur.value:,.0f})."
    return o


def chk_scope_or_retirement(ctx, s: Signal) -> CheckOutcome:
    o = CheckOutcome("scope_or_retirement")
    ev = [e for e in ctx.facts if e.fact_type.value == "event" and
          re.search(r"retire|decommission|divest|joint\s+venture|\bJV\b|subsidiar", e.passage, re.I)]
    if not ev:
        o.note = "No retirement, divestment or JV-scope disclosures found."
        return o
    o.fact_ids = [e.id for e in ev]
    o.effect, o.weight = "opposes", 0.45
    o.note = f"{len(ev)} disclosure(s) mention retirements, divestments or JV structures that could explain the gap."
    return o


def chk_more_periods(ctx, s: Signal) -> CheckOutcome:
    return CheckOutcome("more_periods", "neutral", 0.0, [], "Association re-tested automatically when new periods are collected.")


CHECKS: dict[str, Callable[[AnalysisContext, Signal], CheckOutcome]] = {
    "pipeline_covers_gap": chk_pipeline_covers_gap,
    "recent_commissioning": chk_recent_commissioning,
    "late_year_commissioning": chk_late_year_commissioning,
    "stable_utilisation": chk_stable_utilisation,
    "equity_raise": chk_equity_raise,
    "funding_secured": chk_funding_secured,
    "cash_buffer": chk_cash_buffer,
    "refinancing": chk_refinancing,
    "receivables_falling": chk_receivables_falling,
    "delay_events": chk_delay_events,
    "pipeline_large": chk_pipeline_large,
    "quarterly_rebound": chk_quarterly_rebound,
    "ebitda_absolute_up": chk_ebitda_absolute_up,
    "scope_or_retirement": chk_scope_or_retirement,
    "more_periods": chk_more_periods,
}


# ---------------------------------------------------------------------------------------------
# Evidence grading
# ---------------------------------------------------------------------------------------------

def fact_quality(f: Fact, tier: SourceTier) -> float:
    q = TIER_WEIGHT.get(tier, 0.3)
    q *= 1.0 if f.status == FactStatus.source_verified else 0.4
    q *= 0.85 if f.period_inferred else 1.0
    q *= 0.9 if f.scope == Scope.unknown and f.fact_type.value == "reported" else 1.0
    return q


@dataclass
class Grade:
    score: float
    strength: Strength
    n_facts: int
    n_sources: int
    unverified: list[str]
    conflicted: list[str]
    limitations: list[str]


def grade_evidence(ctx: AnalysisContext, fact_ids: list[str], conflict_ids: set[str],
                   opposing_weight: float = 0.0) -> Grade:
    facts = [ctx.facts_by_id[i] for i in dict.fromkeys(fact_ids) if i in ctx.facts_by_id]
    lim: list[str] = []
    if not facts:
        return Grade(0.0, Strength.insufficient, 0, 0, [], [], ["No supporting facts."])
    quals = [fact_quality(f, ctx.tiers.get(f.source_id, SourceTier.unknown)) for f in facts]
    q = sum(quals) / len(quals)
    srcs = {f.source_id for f in facts}
    diversity = min(1.0, 0.55 + 0.15 * len(srcs))
    unverified = [f.id for f in facts if f.status != FactStatus.source_verified]
    conflicted = [f.id for f in facts if f.id in conflict_ids]
    inferred = [f for f in facts if f.period_inferred]
    score = q * diversity - 0.15 * len(conflicted) - 0.3 * opposing_weight
    score = max(0.0, min(1.0, score))
    if len(srcs) == 1:
        lim.append("All supporting facts come from a single source document.")
    if inferred:
        lim.append(f"{len(inferred)} supporting fact(s) take their period from document context, not the sentence.")
    if unverified:
        lim.append(f"{len(unverified)} supporting fact(s) are not verified verbatim in their source passage.")
    if conflicted:
        lim.append(f"{len(conflicted)} supporting fact(s) conflict with other sources for the same period.")
    tiers = {ctx.tiers.get(f.source_id, SourceTier.unknown) for f in facts}
    if tiers <= {SourceTier.media, SourceTier.unknown}:
        lim.append("No issuer, exchange or regulator source supports this finding.")
    strength = (Strength.strong if score >= 0.65 else Strength.moderate if score >= 0.45 else
                Strength.weak if score >= 0.25 else Strength.insufficient)
    return Grade(round(score, 3), strength, len(facts), len(srcs), unverified, conflicted, lim)


# ---------------------------------------------------------------------------------------------
# Signals -> hypotheses
# ---------------------------------------------------------------------------------------------

GENERIC_COUNTER = {
    "risk": "Alternative explanation: timing effects (commissioning dates, seasonality, one-off items) can produce "
            "the same pattern without an underlying problem.",
    "opportunity": "Alternative explanation: favourable conditions in one period (resource, tariffs, one-offs) may not persist.",
    "neutral": "This is an observation; it does not by itself indicate risk or opportunity.",
}


def conflict_fact_ids(ctx: AnalysisContext, metrics: Optional[list[str]] = None) -> set[str]:
    from .metrics import METRICS
    ids: set[str] = set()
    for m in (metrics or list(METRICS)):
        for per in ("annual", "quarterly"):
            for c in ctx.series(m, per).conflicts:
                ids.update(c.fact_ids)
    return ids


def evaluate_signal(ctx: AnalysisContext, s: Signal, conflicts: set[str], counter_searched: bool,
                    final: bool, statuses: Optional[dict[str, HypothesisStatus]] = None) -> dict:
    """Run counter-checks and grade one signal. Returns fields to set on its Hypothesis."""
    outcomes: list[CheckOutcome] = []
    for name in s.counter_checks:
        if name == "components_hold":
            outcomes.append(_components_hold(s, statuses or {}))
            continue
        fn = CHECKS.get(name)
        if not fn:
            continue
        try:
            outcomes.append(fn(ctx, s))
        except Exception as e:  # a failed check never kills verification
            outcomes.append(CheckOutcome(name, "no_evidence", 0.0, [], f"check failed: {type(e).__name__}"))
    opposing = [o for o in outcomes if o.effect == "opposes"]
    supporting = [o for o in outcomes if o.effect == "supports"]
    opp_w = min(1.0, sum(o.weight for o in opposing))
    g = grade_evidence(ctx, s.supporting_fact_ids, conflicts, opp_w)

    counterargs = [o.note for o in opposing]
    if not counterargs:
        searched = ", ".join(o.check.replace("_", " ") for o in outcomes) or "none defined"
        counterargs.append(f"No opposing evidence found in collected sources (checks: {searched}).")
    counterargs.append(GENERIC_COUNTER.get(s.direction, GENERIC_COUNTER["neutral"]))

    order = ["insufficient", "weak", "moderate", "strong"]
    if s.max_strength in order and order.index(g.strength.value) > order.index(s.max_strength):
        g.strength = Strength(s.max_strength)
        g.limitations.append(f"Strength capped at '{s.max_strength}': small statistical sample.")

    if s.insufficient or g.n_facts == 0:
        status, strength = HypothesisStatus.insufficient_evidence, Strength.insufficient
    elif any(o.weight >= 0.8 for o in opposing):
        status, strength = HypothesisStatus.rejected, g.strength
    elif opp_w >= 0.4:
        status, strength = HypothesisStatus.weakened, g.strength
    elif g.conflicted:
        status, strength = HypothesisStatus.unresolved, g.strength
    elif g.unverified:
        status, strength = HypothesisStatus.unresolved, g.strength
    elif not counter_searched and not final:
        status, strength = HypothesisStatus.proposed, g.strength
    elif g.strength in (Strength.strong, Strength.moderate):
        status, strength = HypothesisStatus.supported, g.strength
    else:
        status, strength = HypothesisStatus.unresolved, g.strength

    counter_facts = sorted({i for o in opposing for i in o.fact_ids})
    support_extra = sorted({i for o in supporting for i in o.fact_ids})
    rank = s.severity * {"strong": 1.0, "moderate": 0.8, "weak": 0.55, "insufficient": 0.3}[strength.value]
    rank *= {HypothesisStatus.rejected: 0.2, HypothesisStatus.weakened: 0.6,
             HypothesisStatus.insufficient_evidence: 0.3}.get(status, 1.0)
    return {
        "status": status, "strength": strength, "score": round(rank, 3),
        "counter_fact_ids": counter_facts,
        "supporting_fact_ids": list(dict.fromkeys(s.supporting_fact_ids + support_extra)),
        "counterarguments": counterargs,
        "limitations": list(dict.fromkeys(s.limitations + g.limitations)),
        "checks": [o.as_dict() for o in outcomes],
        "grade": g,
    }


def _components_hold(s: Signal, statuses: dict[str, HypothesisStatus]) -> CheckOutcome:
    keys = s.params.get("component_keys", [])
    bad = [k for k in keys if statuses.get(k) in (HypothesisStatus.rejected, HypothesisStatus.weakened)]
    o = CheckOutcome("components_hold")
    if not keys:
        return o
    if len(bad) >= 2:
        o.effect, o.weight = "opposes", 0.5
        o.note = f"{len(bad)} of {len(keys)} component findings were weakened or rejected on verification."
    elif bad:
        o.effect, o.weight = "opposes", 0.2
        o.note = f"1 of {len(keys)} component findings was weakened or rejected."
    else:
        o.effect, o.weight = "supports", 0.2
        o.note = f"All {len(keys)} component findings survived verification so far."
    return o


def update_hypotheses(ctx: AnalysisContext, signals: list[Signal], existing: dict[str, Hypothesis],
                      round_no: int, searched_keys: set[str], final: bool,
                      search_available: bool = True) -> list[Hypothesis]:
    """Create or revise one Hypothesis per signal key. Hypotheses whose signal disappeared are marked."""
    conflicts = conflict_fact_ids(ctx)
    out: dict[str, Hypothesis] = {}
    statuses: dict[str, HypothesisStatus] = {}
    ordered = sorted(signals, key=lambda s: s.counter_checks == ["components_hold"])  # composite last
    for s in ordered:
        searched = s.key in searched_keys or not s.counter_queries or not search_available
        ev = evaluate_signal(ctx, s, conflicts, searched, final, statuses)
        h = existing.get(s.key)
        if h is None:
            h = Hypothesis(run_id=ctx.run_id, module=s.module, signal_key=s.key, title=s.title, statement=s.statement,
                           direction=s.direction, round_created=round_no)
            h.history.append(f"R{round_no}: proposed by {s.module}.")
        old_status = h.status
        h.title, h.statement, h.direction = s.title, s.statement, s.direction
        h.calc_ids = list(s.calc_ids)
        h.falsification = s.falsification
        h.counter_queries = list(s.counter_queries)
        h.counter_searched = searched
        h.params = {k: v for k, v in s.params.items() if isinstance(v, (int, float, str, bool, list))}
        for k in ("status", "strength", "score", "counter_fact_ids", "supporting_fact_ids", "counterarguments",
                  "limitations", "checks"):
            setattr(h, k, ev[k])
        if not search_available and s.counter_queries:
            h.limitations = list(dict.fromkeys(h.limitations + [
                "External counter-evidence search was unavailable; only the collected documents were checked."]))
        elif final and not searched:
            h.limitations = list(dict.fromkeys(h.limitations + [
                "Round limit reached before a dedicated counter-evidence search for this finding; "
                "only evidence already collected was checked."]))
        h.round_updated = round_no
        g: Grade = ev["grade"]
        if old_status != h.status or len(h.history) == 1:
            h.history.append(f"R{round_no}: {h.status.value} (strength {h.strength.value}, {g.n_facts} fact(s) from "
                             f"{g.n_sources} source(s); {sum(1 for c in h.checks if c['effect'] == 'opposes')} "
                             f"opposing check(s)).")
        statuses[s.key] = h.status
        out[s.key] = h
    for key, h in existing.items():
        if key in out:
            continue
        if h.status not in (HypothesisStatus.rejected,):
            h.history.append(f"R{round_no}: signal no longer triggered after new evidence was added; rejected.")
            h.status = HypothesisStatus.rejected
            h.score = round(h.score * 0.2, 3)
            h.round_updated = round_no
        out[key] = h
    return sorted(out.values(), key=lambda h: -h.score)


STATUS_LABEL = {
    HypothesisStatus.supported: "Supported",
    HypothesisStatus.proposed: "Pending counter-check",
    HypothesisStatus.weakened: "Weakened",
    HypothesisStatus.rejected: "Rejected",
    HypothesisStatus.unresolved: "Unresolved",
    HypothesisStatus.insufficient_evidence: "Insufficient evidence",
}


def status_label(s) -> str:
    try:
        return STATUS_LABEL[HypothesisStatus(s)]
    except Exception:
        return str(s)


# ---------------------------------------------------------------------------------------------
# Optional LLM interpretation with a numeric guard
# ---------------------------------------------------------------------------------------------

_NUM = re.compile(r"\d[\d,]*\.?\d*")


def guard_numbers(text: str, allowed_text: str) -> bool:
    """True if every number in `text` also appears in `allowed_text` (comma-insensitive)."""
    allowed = {n.replace(",", "").rstrip(".") for n in _NUM.findall(allowed_text)}
    for n in _NUM.findall(text):
        k = n.replace(",", "").rstrip(".")
        if k and k not in allowed:
            return False
    return True


def interpret(h: Hypothesis, ctx: AnalysisContext, llm) -> str:
    """Ask the LLM for a 2–3 sentence interpretation. Rejected if it introduces any new number."""
    if not getattr(llm, "available", False):
        return ""
    facts = [ctx.facts_by_id[i] for i in h.supporting_fact_ids if i in ctx.facts_by_id][:8]
    evidence = "\n".join(f"- {f.passage[:300]}" for f in facts)
    allowed = h.statement + "\n" + evidence + "\n" + "\n".join(h.counterarguments)
    prompt = (f"Finding: {h.statement}\nStatus: {h.status.value}\nEvidence passages:\n{evidence}\n"
              f"Counterarguments:\n" + "\n".join(h.counterarguments) +
              "\n\nWrite 2-3 sentences interpreting what this may mean for an investor. Do not introduce any number "
              "that is not in the text above. Do not claim causation. Mention the main uncertainty.")
    try:
        txt = llm.complete("You are a cautious equity research analyst.", prompt, 300).strip()
    except Exception:
        return ""
    if not txt or not guard_numbers(txt, allowed):
        return ""
    return txt
