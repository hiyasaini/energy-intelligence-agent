"""Capital and Cash: capex, debt, finance costs, cash generation and funding capacity."""
from __future__ import annotations

from ..calculations import Point
from ..metrics import metric_label
from ..periods import period_sort_key
from .base import AnalysisContext, ModuleResult, Signal, fmt, latest_two

KEY, NAME = "capital_cash", "Capital and Cash"
METRICS_USED = ["capex_cr", "gross_debt_cr", "net_debt_cr", "cash_cr", "finance_cost_cr", "cfo_cr",
                "ebitda_cr", "equity_cr", "pat_cr"]
LEVERAGE_HIGH = 5.0      # debt / EBITDA
COVERAGE_LOW = 2.0       # EBITDA / finance cost
CONVERSION_LOW = 0.7     # CFO / EBITDA


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(KEY, NAME)
    calc = ctx.calculator(KEY)
    co = ctx.company.name
    S = {}
    for m in METRICS_USED:
        s = ctx.series(m)
        res.relationships += ctx.conflict_relationships(s, KEY)
        if len(s):
            S[m] = s
            res.series[m] = s
            res.notes += s.warnings
        else:
            res.missing.append(metric_label(m))

    debt_key = "net_debt_cr" if "net_debt_cr" in S else ("gross_debt_cr" if "gross_debt_cr" in S else None)
    periods = sorted({p for s in S.values() for p in s.periods}, key=period_sort_key)

    def pt(m, p) -> Point | None:
        return S[m].get(p) if m in S else None

    ratio_rows = {}
    for p in periods[-4:]:
        row = {"period": p}
        if debt_key:
            r = calc.ratio(f"{metric_label(debt_key)} / EBITDA {p}", pt(debt_key, p), pt("ebitda_cr", p),
                           formula=f"{debt_key} / ebitda")
            row["debt_to_ebitda"] = r
        r = calc.ratio(f"Interest coverage {p}", pt("ebitda_cr", p), pt("finance_cost_cr", p),
                       formula="ebitda / finance_cost")
        row["interest_coverage"] = r
        if pt("cfo_cr", p) and pt("capex_cr", p):
            row["fcf"] = calc.difference(f"Free cash flow {p}", pt("cfo_cr", p), pt("capex_cr", p), "cfo - capex")
        row["cash_conversion"] = calc.ratio(f"CFO / EBITDA {p}", pt("cfo_cr", p), pt("ebitda_cr", p),
                                            formula="cfo / ebitda")
        if "gross_debt_cr" in S:
            row["cost_of_debt"] = calc.ratio(f"Implied cost of debt {p}", pt("finance_cost_cr", p),
                                             pt("gross_debt_cr", p), unit="%", scale=100,
                                             formula="finance_cost / period-end gross debt × 100")
        if debt_key and "equity_cr" in S:
            row["debt_to_equity"] = calc.ratio(f"Debt / equity {p}", pt(debt_key, p), pt("equity_cr", p),
                                               formula=f"{debt_key} / equity")
        ratio_rows[p] = row
        res.rows.append({"period": p, **{k: (fmt(v.result, v.unit, 2) if v.result is not None else
                                             ("Insufficient evidence" if v.status == "insufficient_data" else v.status))
                                         for k, v in row.items() if k != "period"}})

    # --- signals ------------------------------------------------------------------------
    latest_p = periods[-1] if periods else None
    lr = ratio_rows.get(latest_p, {}) if latest_p else {}

    lev = lr.get("debt_to_ebitda")
    if lev is not None and lev.result is not None and lev.result >= LEVERAGE_HIGH:
        res.signals.append(Signal(
            key=f"{KEY}:leverage", module=KEY, title=f"High leverage: {lev.result:.1f}x debt to EBITDA",
            statement=f"{metric_label(debt_key)} is {lev.result:.1f}x EBITDA in {latest_p}, above the "
                      f"{LEVERAGE_HIGH:.0f}x level usually treated as stretched for power companies.",
            direction="risk", severity=min(0.9, 0.4 + lev.result / 20), supporting_fact_ids=lev.input_fact_ids,
            calc_ids=[lev.id],
            limitations=["Contracted, long-tenor renewable assets often carry higher leverage than merchant assets.",
                         "EBITDA from newly commissioned assets is only partially reflected in the year."],
            falsification="Weakened by a disclosed equity raise or by debt/EBITDA falling below 5x in the next period.",
            counter_checks=["equity_raise", "cash_buffer"],
            counter_queries=[f"{co} QIP equity raise", f"{co} credit rating rationale", f"{co} net debt reduction"]))

    cov = lr.get("interest_coverage")
    if cov is not None and cov.result is not None and cov.result < COVERAGE_LOW:
        res.signals.append(Signal(
            key=f"{KEY}:coverage", module=KEY, title=f"Thin interest coverage: {cov.result:.2f}x",
            statement=f"EBITDA covers finance costs {cov.result:.2f} times in {latest_p}.",
            direction="risk", severity=min(0.9, 0.5 + (COVERAGE_LOW - cov.result) / 4),
            supporting_fact_ids=cov.input_fact_ids, calc_ids=[cov.id],
            limitations=["Capitalised interest on projects under construction is excluded from P&L finance cost."],
            falsification="Rejected if coverage exceeds 2x in the following period or a refinancing lowers costs.",
            counter_checks=["equity_raise", "refinancing"],
            counter_queries=[f"{co} refinancing lower interest", f"{co} credit rating upgrade"]))

    conv = lr.get("cash_conversion")
    if conv is not None and conv.result is not None and conv.result < CONVERSION_LOW:
        res.signals.append(Signal(
            key=f"{KEY}:conversion", module=KEY, title=f"Weak cash conversion: CFO is {conv.result:.0%} of EBITDA",
            statement=f"Operating cash flow was {conv.result:.0%} of EBITDA in {latest_p}; profits are not fully "
                      "turning into cash.",
            direction="risk", severity=0.55, supporting_fact_ids=conv.input_fact_ids, calc_ids=[conv.id],
            limitations=["Working-capital swings (e.g., late DISCOM payments that are later recovered) can be temporary."],
            falsification="Weakened if CFO/EBITDA recovers above 0.8 in the next period or receivables fall.",
            counter_checks=["receivables_falling"],
            counter_queries=[f"{co} receivables DISCOM dues recovered", f"{co} late payment surcharge"]))

    fcfs = [(p, r["fcf"]) for p, r in ratio_rows.items() if "fcf" in r and r["fcf"].result is not None]
    neg = [x for x in fcfs if x[1].result < 0]
    if len(fcfs) >= 2 and len(neg) >= 2 and neg[-1][0] == fcfs[-1][0]:
        res.signals.append(Signal(
            key=f"{KEY}:fcf_negative", module=KEY,
            title=f"Free cash flow negative in {len(neg)} of {len(fcfs)} periods",
            statement="Capex has exceeded operating cash flow repeatedly, so growth is being funded externally.",
            direction="risk", severity=0.5, supporting_fact_ids=[i for _, c in neg for i in c.input_fact_ids],
            calc_ids=[c.id for _, c in neg],
            limitations=["Negative FCF is expected during a build-out; the question is funding, not the sign itself."],
            falsification="Weakened if funding (equity, long-tenor debt) is already tied up for the capex programme.",
            counter_checks=["equity_raise", "funding_secured"],
            counter_queries=[f"{co} funding tie-up capex", f"{co} green bond raise"]))

    # debt growing faster than EBITDA
    if debt_key and "ebitda_cr" in S:
        dc = calc.cagr(f"{metric_label(debt_key)} CAGR", S[debt_key])
        ec = calc.cagr("EBITDA CAGR", S["ebitda_cr"])
        if dc.result is not None and ec.result is not None:
            res.rows.append({"period": "trend", "debt_cagr": fmt(dc.result, "%"), "ebitda_cagr": fmt(ec.result, "%")})
            if dc.result - ec.result >= 10:
                res.signals.append(Signal(
                    key=f"{KEY}:debt_outpaces_ebitda", module=KEY, title="Debt is growing faster than EBITDA",
                    statement=f"{metric_label(debt_key)} CAGR {dc.result:.1f}% vs EBITDA CAGR {ec.result:.1f}% "
                              f"({dc.period}).",
                    direction="risk", severity=min(0.85, 0.4 + (dc.result - ec.result) / 50),
                    supporting_fact_ids=dc.input_fact_ids + ec.input_fact_ids, calc_ids=[dc.id, ec.id],
                    limitations=["Debt for assets under construction precedes their EBITDA by 1–3 years."],
                    falsification="Weakened if capacity under construction is large relative to operating capacity "
                                  "(debt ahead of EBITDA) and rejected if EBITDA growth catches up next period.",
                    counter_checks=["pipeline_large", "equity_raise"],
                    counter_queries=[f"{co} capacity under construction", f"{co} equity infusion"]))
            elif ec.result - dc.result >= 10:
                res.signals.append(Signal(
                    key=f"{KEY}:deleveraging", module=KEY, title="EBITDA growing faster than debt",
                    statement=f"EBITDA CAGR {ec.result:.1f}% exceeds {metric_label(debt_key)} CAGR {dc.result:.1f}%, "
                              "consistent with improving debt capacity.",
                    direction="opportunity", severity=0.4, supporting_fact_ids=dc.input_fact_ids + ec.input_fact_ids,
                    calc_ids=[dc.id, ec.id], limitations=["One-off EBITDA items can flatter the trend."],
                    falsification="Weakened if a large debt-funded acquisition or capex plan is announced.",
                    counter_checks=["funding_secured"], counter_queries=[f"{co} acquisition debt funded"]))

    # finance cost growth vs revenue growth (latest)
    if "finance_cost_cr" in S and "revenue_cr" in S:
        fp, fc = latest_two(S["finance_cost_cr"])
        rp, rc = latest_two(S["revenue_cr"])
        g1 = calc.growth("Finance cost YoY", fp, fc)
        g2 = calc.growth("Revenue YoY (capital module)", rp, rc)
        if g1.result is not None and g2.result is not None and g1.period == g2.period and g1.result - g2.result >= 15:
            res.signals.append(Signal(
                key=f"{KEY}:finance_cost_outpaces_revenue", module=KEY, title="Finance costs rising faster than revenue",
                statement=f"Finance costs grew {g1.result:.1f}% vs revenue {g2.result:.1f}% in {g1.period}.",
                direction="risk", severity=0.5, supporting_fact_ids=g1.input_fact_ids + g2.input_fact_ids,
                calc_ids=[g1.id, g2.id], limitations=["Interest on newly capitalised projects moves from balance sheet to P&L at COD."],
                falsification="Weakened if new assets reaching COD explain the step-up and revenue follows next period.",
                counter_checks=["recent_commissioning"], counter_queries=[f"{co} commercial operation date"]))

    res.calcs = calc.records
    have = len(S)
    res.status = "insufficient_data" if have == 0 else ("ok" if have >= 5 else "partial")
    res.summary = (f"{have}/{len(METRICS_USED)} capital metrics found across {len(periods)} period(s)."
                   if have else "Insufficient evidence: no capex, debt, finance cost or cash-flow figures found.")
    return res
