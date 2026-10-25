"""Promise vs Reality: stated targets compared with disclosed outcomes and historical delivery pace."""
from __future__ import annotations

from collections import defaultdict

from ..metrics import TARGET_BASE, metric_label
from ..periods import period_sort_key
from .base import AnalysisContext, ModuleResult, Signal, fmt

KEY, NAME = "promise_reality", "Promise vs Reality"

# which actual series a target is measured against (first available wins)
ACTUAL_FOR = {
    "renewable_target_mw": ["renewable_capacity_mw", "installed_capacity_mw"],
    "capacity_target_mw": ["installed_capacity_mw", "renewable_capacity_mw"],
    "generation_target_mu": ["generation_mu"],
    "revenue_target_cr": ["revenue_cr"],
    "capex_target_cr": ["capex_cr"],
    "coal_target_mt": ["coal_production_mt", "coal_offtake_mt"],
    "oil_gas_target_mtoe": ["oil_gas_production_mtoe"],
    "refining_target_mt": ["refinery_throughput_mt"],
    "transmission_target_ckm": ["transmission_ckm"],
    "transformation_target_mva": ["transformation_mva"],
}
PACE_RISK = 1.5      # required pace / historical pace above which delivery is at risk
TARGET_SCALE_MAX = 20.0    # a company plan can be ambitious (SJVN-style 10x growth plans exist); 20x its base is not a plan
MIN_POWER_BASE_MW = 1000.0  # below this, "installed capacity" is a side portfolio, not the company's base


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    targets = ctx.targets(list(TARGET_BASE))
    if not targets:
        res.status = "insufficient_data"
        res.summary = "Insufficient evidence: no dated targets or guidance were found in the collected sources."
        res.missing = ["any dated target (capacity / capex / generation)"]
        return res

    # group restatements of the same target (same metric & year)
    groups: dict[tuple, list] = defaultdict(list)
    for t in targets:
        groups[(t.metric, t.target_year)].append(t)

    for (tmetric, tyear), ts in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        # a target above any Indian company's scale (e.g. India's 500 GW goal quoted in a report) is not the company's
        from ..sanity import ABS_MAX
        cap_abs = ABS_MAX.get(ACTUAL_FOR.get(tmetric, [""])[0])
        big = [t for t in ts if cap_abs and t.value > cap_abs]
        if big:
            res.notes.append(f"{metric_label(tmetric)} of {fmt(max(t.value for t in big), big[0].unit)} by {tyear} is above "
                             "any Indian company's scale; held out as it is most likely a national or sector goal quoted "
                             "in the report, not the company's own target.")
            ts = [t for t in ts if t not in big]
            if not ts:
                continue
        ts = sorted(ts, key=lambda f: (f.period_end or "", f.confidence))
        target = ts[-1]  # most recently stated
        top = max(t.value for t in ts)
        # values far below the others are a different quantity (a single project, a current level), not a revision
        distinct = sorted({round(t.value, 2) for t in ts if t.value >= 0.1 * top})
        if len(distinct) > 1:
            res.signals.append(Signal(
                key=f"{KEY}:revision:{tmetric}:{tyear}", module=KEY,
                title=f"{metric_label(tmetric)} for {tyear} stated with different values",
                statement=f"Sources state {metric_label(tmetric).lower()} for {tyear} as "
                          f"{', '.join(fmt(v, target.unit) for v in distinct)}. This may be a revision or a scope "
                          "difference; it is not, by itself, evidence of under-delivery.",
                direction="neutral", severity=0.35, supporting_fact_ids=[t.id for t in ts],
                limitations=["Values may refer to different scopes (group vs listed entity) or gross vs net capacity."],
                falsification="Resolved if a single source explains the change (e.g., formal revision announcement).",
                counter_queries=[f"{co} revised target {tyear}"]))

        actual_metric = next((m for m in ACTUAL_FOR.get(tmetric, []) if ctx.has(m)), None)
        row = {"target": metric_label(tmetric), "target_value": fmt(target.value, target.unit),
               "target_year": tyear, "stated_in": target.period or "unknown"}
        if not actual_metric:
            row.update({"actual": "n/a", "status": "Insufficient evidence"})
            res.rows.append(row)
            res.missing.append(f"actuals for {metric_label(tmetric)}")
            res.signals.append(Signal(
                key=f"{KEY}:untracked:{tmetric}:{tyear}", module=KEY,
                title=f"{metric_label(tmetric)} ({tyear}) cannot be tracked yet",
                statement=f"{co} states a target of {fmt(target.value, target.unit)} by {tyear}, but no comparable "
                          "disclosed outcome was found, so progress is unresolved.",
                direction="neutral", severity=0.2, supporting_fact_ids=[target.id], insufficient=True,
                falsification="n/a — needs disclosed actuals.",
                counter_queries=[f"{co} {metric_label(ACTUAL_FOR.get(tmetric, ['capacity'])[0])}"]))
            continue

        series = ctx.series(actual_metric)
        current = ctx.latest_point(actual_metric)
        lim = ["Check that target and actual cover the same entity (group vs listed company) and capacity basis "
               "(AC/DC, gross/attributable)."]
        if actual_metric != ACTUAL_FOR[tmetric][0]:
            lim.append(f"Measured against {metric_label(actual_metric)} because the more specific metric was not found.")
        # Scale check: a target many times the company's whole current base is most likely a national goal quoted in
        # the report. It is applied only where the base is the company's main business: total capacity targets of a
        # real power producer (>= MIN_POWER_BASE_MW), and production / network targets measured on their own metric.
        # Renewable targets are not scale-checked: oil, gas and coal companies build them from a tiny base (a 31 GW
        # goal from 0.25 GW is a genuine plan); national renewable goals are filtered by wording at extraction.
        whole_metric, whole = None, None
        if tmetric == "capacity_target_mw" and ctx.has("installed_capacity_mw"):
            whole_metric = "installed_capacity_mw"
        elif tmetric not in ("renewable_target_mw", "capacity_target_mw", "capex_target_cr") and \
                actual_metric == ACTUAL_FOR[tmetric][0]:
            whole_metric = actual_metric
        if whole_metric:
            whole = ctx.latest_point(whole_metric)
            if whole and whole_metric == "installed_capacity_mw" and whole.value < MIN_POWER_BASE_MW:
                whole = None
        mult = mult_whole = target.value / whole.value if whole and whole.value > 0 else 0
        if mult_whole > TARGET_SCALE_MAX:
            current, actual_metric = whole, whole_metric
            row.update({"actual": fmt(current.value, current.unit) + f" ({current.period})",
                        "status": f"Held out: {mult:.1f}x the current level"})
            res.rows.append(row)
            res.notes.append(f"{metric_label(tmetric)} of {fmt(target.value, target.unit)} by {tyear} is {mult:.1f}x the "
                                f"latest {metric_label(actual_metric).lower()}; held out as it is most likely a national "
                                "or sector goal quoted in the report, not the company's own target.")
            continue
        if tmetric == "capex_target_cr":
            hist = calc.cagr(f"{metric_label(actual_metric)} CAGR", series)
            cur = current
            # capex plans are usually cumulative: compare required average annual capex with recent annual capex
            years_left = tyear - period_sort_key(cur.period)[0] if cur else 0
            if cur and years_left > 0:
                req = calc._rec(name="Capex plan — required average annual spend", formula="plan / years_remaining",
                                input_fact_ids=[target.id], inputs={"plan": target.value, "years_remaining": years_left},
                                result=target.value / years_left, unit="INR_cr/yr", period=cur.period,
                                notes="Assumes the plan is cumulative from the latest reported year.")
                ratio = req.result / cur.value if cur.value else None
                r = calc._rec(name="Capex plan — required vs latest annual capex", formula="required_annual / latest_capex",
                              input_fact_ids=[cur.fact_id], input_calc_ids=[req.id],
                              inputs={"required_annual": req.result, f"capex {cur.period}": cur.value},
                              result=ratio, unit="x", period=cur.period)
                row.update({"actual": fmt(cur.value, cur.unit) + f" ({cur.period})",
                            "required_pace": fmt(req.result, "INR_cr") + "/yr",
                            "pace_multiple": fmt(ratio, "x", 2) if ratio else "n/a"})
                if ratio and ratio > 1.3:
                    res.signals.append(Signal(
                        key=f"{KEY}:capex_step_up:{tyear}", module=KEY,
                        title=f"Capex plan implies a {ratio:.1f}x step-up in annual spending",
                        statement=f"The stated plan of {fmt(target.value, 'INR_cr')} by {tyear} implies about "
                                  f"{fmt(req.result, 'INR_cr')} a year versus {fmt(cur.value, 'INR_cr')} in {cur.period}. "
                                  "Funding the gap will depend on cash generation and new borrowing or equity.",
                        direction="risk", severity=min(0.9, 0.4 + 0.1 * ratio),
                        supporting_fact_ids=[target.id, cur.fact_id], calc_ids=[req.id, r.id],
                        limitations=lim + ["Plan may include group/JV spending or be non-cumulative."],
                        falsification="Weakened if annual capex in the next year rises to the required pace, "
                                      "or the plan is shown to cover a different scope.",
                        counter_checks=["funding_secured"],
                        counter_queries=[f"{co} fund raise QIP equity", f"{co} capex funding plan debt"],
                        params={"required_annual": req.result}))
            res.rows.append(row)
            continue

        hist_rate = calc.avg_annual_addition(f"{metric_label(actual_metric)} — historical annual addition", series)
        pcs = calc.target_progress(f"{metric_label(tmetric)} {tyear}", target, current, hist_rate)
        ach = pcs[0]
        req = pcs[1] if len(pcs) > 1 else None
        row.update({"actual": fmt(current.value, current.unit) + f" ({current.period})" if current else "n/a",
                    "achieved": fmt(ach.result, "%") if ach.result is not None else ach.status,
                    "required_pace": fmt(req.result, target.unit) + "/yr" if req and req.result is not None else "n/a",
                    "historical_pace": fmt(hist_rate.result, target.unit) + "/yr" if hist_rate.result is not None
                    else "Insufficient evidence"})
        if req is None or req.result is None or ach.result is None:
            row["status"] = "Insufficient evidence"
            res.rows.append(row)
            continue
        ids = [target.id, current.fact_id]
        calc_ids = [ach.id, req.id] + ([hist_rate.id] if hist_rate.result is not None else [])
        gap = target.value - current.value
        if hist_rate.result is None or hist_rate.result <= 0:
            row["status"] = "Unresolved"
            res.signals.append(Signal(
                key=f"{KEY}:pace:{tmetric}:{tyear}", module=KEY,
                title=f"{metric_label(tmetric)} {tyear}: delivery pace unresolved",
                statement=f"{co} is at {ach.result:.0f}% of its {tyear} target; there is not enough history to "
                          "compare the required pace with past delivery.",
                direction="neutral", severity=0.3, supporting_fact_ids=ids, calc_ids=calc_ids, insufficient=True,
                limitations=lim + ["Needs at least two annual observations of the actual metric."],
                falsification="n/a — needs a longer history."))
            res.rows.append(row)
            continue
        multiple = req.result / hist_rate.result
        row["pace_multiple"] = f"{multiple:.2f}x"
        if multiple >= PACE_RISK:
            row["status"] = "At risk"
            res.signals.append(Signal(
                key=f"{KEY}:pace:{tmetric}:{tyear}", module=KEY,
                title=f"{metric_label(tmetric)} needs {multiple:.1f}x the historical build pace",
                statement=f"Reaching {fmt(target.value, target.unit)} by {tyear} from {fmt(current.value, current.unit)} "
                          f"({current.period}) requires about {fmt(req.result, target.unit)}/yr, versus a historical "
                          f"{fmt(hist_rate.result, target.unit)}/yr.",
                direction="risk", severity=min(0.95, 0.45 + 0.1 * multiple), supporting_fact_ids=ids,
                calc_ids=calc_ids,
                limitations=lim + ["Historical pace is a simple average; acquisitions or a large pipeline can change it.",
                                   "Target year is treated as fiscal year-end; calendar-year targets shift this by 3 months."],
                falsification=f"Rejected if capacity under construction (with CODs before {tyear}) covers the remaining "
                              f"gap of {fmt(gap, target.unit)}, or if the next annual addition reaches the required pace.",
                counter_checks=["pipeline_covers_gap", "recent_commissioning"],
                counter_queries=[f"{co} capacity under construction pipeline", f"{co} commissioned capacity {tyear - 5}",
                                 f"{co} investor presentation project pipeline"],
                params={"gap": gap, "required_rate": req.result, "as_of": current.period, "target_year": tyear}))
        else:
            row["status"] = "On historical pace"
            res.signals.append(Signal(
                key=f"{KEY}:pace:{tmetric}:{tyear}", module=KEY,
                title=f"{metric_label(tmetric)} achievable at historical pace",
                statement=f"Required pace ({fmt(req.result, target.unit)}/yr) is within {multiple:.1f}x of historical "
                          f"delivery ({fmt(hist_rate.result, target.unit)}/yr).",
                direction="opportunity", severity=0.4, supporting_fact_ids=ids, calc_ids=calc_ids,
                limitations=lim + ["Past pace does not guarantee future execution (land, transmission, financing)."],
                falsification="Weakened if the next reported addition falls below the required pace or delays are disclosed.",
                counter_checks=["delay_events"],
                counter_queries=[f"{co} project delay", f"{co} commissioning delayed transmission"]))
        res.rows.append(row)

    res.calcs = calc.records
    n_ok = sum(1 for r in res.rows if r.get("status") not in ("Insufficient evidence",))
    res.status = "ok" if n_ok and not res.missing else ("partial" if n_ok else "insufficient_data")
    res.summary = f"{len(groups)} target(s) found; {n_ok} could be compared with disclosed outcomes."
    return res
