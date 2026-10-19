"""View-model functions shared by the Streamlit dashboard and the report exporter.

Pure functions over the SQLite store: no Streamlit imports, so everything here is unit-testable.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import re

import pandas as pd

from .db import Store
from .metrics import METRICS, metric_label
from .modules import MODULE_NAMES, AnalysisContext
from .periods import is_annual, is_quarter, period_end, period_sort_key
from .schema import FactStatus, FactType, Hypothesis, HypothesisStatus
from .verification import status_label

EPISTEMIC = {
    "fact_verified": "Verified fact — value located verbatim in the cited passage",
    "fact_unverified": "Unverified claim — extracted but not located verbatim",
    "calculation": "Calculated result — deterministic Python over cited facts",
    "hypothesis": "Hypothesis — a claim under test, with status and evidence strength",
    "interpretation": "Interpretation — narrative; never a source of numbers",
}


def run_summary(store: Store, run_id: str) -> dict:
    run = store.get_run(run_id)
    srcs = store.sources(run_id)
    facts = store.facts(run_id)
    hyps = store.hypotheses(run_id)
    by_status = defaultdict(int)
    for h in hyps:
        by_status[status_label(h.status)] += 1
    reported = [f for f in facts if f.fact_type == FactType.reported]
    return {
        "run": run,
        "company": run.company if run else None,
        "mode": run.mode if run else "",
        "status": run.status if run else "",
        "rounds": run.rounds_completed if run else 0,
        "sources_ok": sum(1 for s in srcs if s.fetch_status == "ok"),
        "sources_failed": sum(1 for s in srcs if s.fetch_status == "failed"),
        "sources_total": len(srcs),
        "facts": len(facts),
        "facts_verified": sum(1 for f in facts if f.status == FactStatus.source_verified),
        "targets": sum(1 for f in facts if f.fact_type == FactType.target),
        "events": sum(1 for f in facts if f.fact_type == FactType.event),
        "metrics_covered": len({f.metric for f in reported}),
        "periods_covered": sorted({f.period for f in reported if f.period}, key=period_sort_key),
        "hypotheses": len(hyps),
        "by_status": dict(by_status),
        "risks": sum(1 for h in hyps if h.direction == "risk" and h.status == HypothesisStatus.supported),
        "opportunities": sum(1 for h in hyps if h.direction == "opportunity" and h.status == HypothesisStatus.supported),
        "unresolved": sum(1 for h in hyps if h.status in (HypothesisStatus.unresolved, HypothesisStatus.proposed,
                                                          HypothesisStatus.insufficient_evidence)),
    }


def findings_df(store: Store, run_id: str) -> pd.DataFrame:
    rows = []
    for rank, h in enumerate(store.hypotheses(run_id), 1):
        rows.append({"rank": rank, "id": h.id, "title": h.title, "module": MODULE_NAMES.get(h.module, h.module),
                     "direction": h.direction, "status": status_label(h.status), "strength": h.strength.value,
                     "score": h.score, "supporting_facts": len(h.supporting_fact_ids),
                     "counter_facts": len(h.counter_fact_ids), "calcs": len(h.calc_ids),
                     "rounds": f"R{h.round_created}→R{h.round_updated}"})
    return pd.DataFrame(rows)


def _fact_row(f, sources) -> dict:
    s = sources.get(f.source_id)
    return {"id": f.id, "metric": metric_label(f.metric) if f.metric != "event" else f"event: {f.event_category}",
            "metric_key": f.metric, "type": f.fact_type.value,
            "value": f.value, "unit": f.unit, "raw": f"{f.raw_value} {f.raw_unit}".strip(), "period": f.period,
            "period_inferred": f.period_inferred, "target_year": f.target_year, "scope": f.scope.value,
            "status": f.status.value,
            "epistemic": EPISTEMIC["fact_verified" if f.status == FactStatus.source_verified else "fact_unverified"],
            "method": f.extraction_method, "confidence": f.confidence, "page": f.page, "passage": f.passage,
            "source_id": f.source_id, "source_title": s.title if s else "", "source_url": s.url if s else "",
            "source_tier": s.tier.value if s else "", "doc_type": s.doc_type.value if s else "",
            "published": (s.published or "") if s else ""}


def passport(store: Store, run_id: str, hyp_id: str) -> Optional[dict]:
    """Evidence Passport: everything needed to audit one finding."""
    h = next((x for x in store.hypotheses(run_id) if x.id == hyp_id), None)
    if not h:
        return None
    facts = {f.id: f for f in store.facts(run_id)}
    sources = {s.id: s for s in store.sources(run_id)}
    calcs = {c.id: c for c in store.calculations(run_id)}
    sup = [_fact_row(facts[i], sources) for i in h.supporting_fact_ids if i in facts]
    cnt = [_fact_row(facts[i], sources) for i in h.counter_fact_ids if i in facts]
    calc_rows = []
    for cid in h.calc_ids:
        c = calcs.get(cid)
        if not c:
            continue
        calc_rows.append({"id": c.id, "name": c.name, "formula": c.formula, "inputs": c.inputs, "result": c.result,
                          "unit": c.unit, "period": c.period, "status": c.status, "notes": c.notes,
                          "input_fact_ids": store.calc_input_facts(c.id), "input_calc_ids": c.input_calc_ids,
                          "epistemic": EPISTEMIC["calculation"]})
    src_ids = list(dict.fromkeys([r["source_id"] for r in sup + cnt]))
    return {
        "hypothesis": h, "status_label": status_label(h.status), "supporting": sup, "counter": cnt,
        "calculations": calc_rows, "sources": [sources[i] for i in src_ids if i in sources],
        "counterarguments": h.counterarguments, "limitations": h.limitations, "falsification": h.falsification,
        "checks": h.checks, "history": h.history, "interpretation": h.interpretation,
        "strength": h.strength.value, "missing_calc_ids": [c for c in h.calc_ids if c not in calcs],
    }


def facts_df(store: Store, run_id: str, query: str = "", metrics: Optional[list[str]] = None,
             types: Optional[list[str]] = None, statuses: Optional[list[str]] = None) -> pd.DataFrame:
    sources = {s.id: s for s in store.sources(run_id)}
    rows = [_fact_row(f, sources) for f in store.facts(run_id)]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if metrics:
        df = df[df["metric_key"].isin(metrics)]
    if types:
        df = df[df["type"].isin(types)]
    if statuses:
        df = df[df["status"].isin(statuses)]
    if query:
        q = query.lower()
        mask = df.apply(lambda r: q in " ".join(str(v) for v in r.values).lower(), axis=1)
        df = df[mask]
    return df.sort_values(["metric", "period"]).reset_index(drop=True)


def sources_df(store: Store, run_id: str) -> pd.DataFrame:
    facts = store.facts(run_id)
    n = defaultdict(int)
    for f in facts:
        n[f.source_id] += 1
    return pd.DataFrame([{"id": s.id, "title": s.title, "url": s.url, "doc_type": s.doc_type.value,
                          "tier": s.tier.value, "published": s.published or "", "status": s.fetch_status,
                          "error": s.error, "pages": s.n_pages, "facts": n.get(s.id, 0), "round": s.round,
                          "purpose": s.purpose, "query": s.query} for s in store.sources(run_id)])


def calculations_df(store: Store, run_id: str, module: Optional[str] = None) -> pd.DataFrame:
    rows = [{"id": c.id, "module": MODULE_NAMES.get(c.module, c.module), "name": c.name, "formula": c.formula,
             "result": c.result, "unit": c.unit, "period": c.period, "status": c.status, "notes": c.notes,
             "inputs": ", ".join(f"{k}={v:,.2f}" if isinstance(v, (int, float)) else f"{k}={v}"
                                 for k, v in c.inputs.items()),
             "input_facts": len(c.input_fact_ids)}
            for c in store.calculations(run_id) if module is None or c.module == module]
    return pd.DataFrame(rows)


def context(store: Store, run_id: str) -> AnalysisContext:
    run = store.get_run(run_id)
    return AnalysisContext(run_id, run.company, store.facts(run_id), store.sources(run_id))


def metric_series_df(store: Store, run_id: str, metric_keys: list[str], periodicity: str = "annual") -> pd.DataFrame:
    """Selected (best-ranked) value per period, as used by the modules."""
    ctx = context(store, run_id)
    rows = []
    for m in metric_keys:
        s = ctx.series(m, periodicity)
        for p in s.points:
            rows.append({"metric": metric_label(m), "metric_key": m, "period": p.period, "value": p.value,
                         "unit": p.unit, "scope": p.scope, "fact_id": p.fact_id,
                         "order": period_sort_key(p.period)})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("order").drop(columns="order")
    return df


def contradictions(store: Store, run_id: str) -> list[dict]:
    """Same metric/period, materially different values across sources."""
    ctx = context(store, run_id)
    sources = {s.id: s for s in store.sources(run_id)}
    out = []
    for m in METRICS:
        for per in ("annual", "quarterly"):
            for c in ctx.series(m, per).conflicts:
                facts = [ctx.facts_by_id[i] for i in c.fact_ids if i in ctx.facts_by_id]
                selected = ctx.series(m, per).get(c.period)
                out.append({"metric": metric_label(m), "period": c.period, "rel_diff_pct": round(c.rel_diff * 100, 2),
                            "scope": c.scope, "selected_fact_id": selected.fact_id if selected else None,
                            "facts": [_fact_row(f, sources) for f in facts]})
    return out


def contested_hypotheses(store: Store, run_id: str) -> list[dict]:
    """Hypotheses with both supporting and opposing evidence (or opposing checks)."""
    out = []
    for h in store.hypotheses(run_id):
        opp = [c for c in h.checks if c.get("effect") == "opposes"]
        sup = [c for c in h.checks if c.get("effect") == "supports"]
        if opp or h.counter_fact_ids or h.status in (HypothesisStatus.weakened, HypothesisStatus.rejected,
                                                     HypothesisStatus.unresolved):
            out.append({"id": h.id, "title": h.title, "status": status_label(h.status), "strength": h.strength.value,
                        "supporting_checks": sup, "opposing_checks": opp, "n_supporting_facts": len(h.supporting_fact_ids),
                        "n_counter_facts": len(h.counter_fact_ids), "statement": h.statement,
                        "falsification": h.falsification, "history": h.history})
    return out


UNIT_SHORT = {"INR_cr": "₹ cr", "MW": "MW", "MU": "MU", "%": "%", "x": "x", "tCO2/MWh": "tCO2/MWh"}
LANES = {"target": "Promise / target", "event": "Milestone / announcement", "operating": "Operating result",
         "financial": "Financial result"}
OPERATING = {"installed_capacity_mw", "renewable_capacity_mw", "generation_mu", "plf_cuf_pct",
             "capacity_under_construction_mw"}


def timeline_df(store: Store, run_id: str) -> pd.DataFrame:
    """Promise-to-Cash timeline: targets, events, operating and financial results placed on dates."""
    sources = {s.id: s for s in store.sources(run_id)}
    ctx = context(store, run_id)
    rows = []
    for f in ctx.facts:
        if f.fact_type == FactType.event:
            if not f.period_end:
                continue
            lane = "Financing" if f.event_category in ("financing", "rating") else LANES["event"]
            label = f"{f.event_category}: {f.passage[:110]}"
            date = f.period_end
        elif f.fact_type == FactType.target:
            lane = LANES["target"]
            date = period_end(f.period) or (sources[f.source_id].published if f.source_id in sources else None)
            if not date:
                continue
            label = f"{metric_label(f.metric)}: {f.value:,.0f} {UNIT_SHORT.get(f.unit, f.unit)} by {f.target_year}"
        else:
            continue
        s = sources.get(f.source_id)
        rows.append({"date": date, "lane": lane, "label": label, "value": f.value, "unit": f.unit,
                     "fact_id": f.id, "source": s.title if s else "", "url": s.url if s else "", "page": f.page,
                     "status": f.status.value})
    # one point per (metric, period) for key results, using the module-selected value
    for m in ["renewable_capacity_mw", "installed_capacity_mw", "generation_mu", "revenue_cr", "ebitda_cr",
              "cfo_cr", "capex_cr", "gross_debt_cr", "finance_cost_cr"]:
        for per in ("annual", "quarterly"):
            for p in ctx.series(m, per).points:
                f = ctx.facts_by_id.get(p.fact_id)
                s = sources.get(f.source_id) if f else None
                rows.append({"date": period_end(p.period), "lane": LANES["operating" if m in OPERATING else "financial"],
                             "label": f"{metric_label(m)} {p.period}: {p.value:,.0f} {UNIT_SHORT.get(p.unit, p.unit)}",
                             "value": p.value,
                             "unit": p.unit, "fact_id": p.fact_id, "source": s.title if s else "",
                             "url": s.url if s else "", "page": f.page if f else None,
                             "status": f.status.value if f else ""})
    # target deadlines as future markers
    for f in ctx.targets():
        rows.append({"date": f"{f.target_year}-03-31", "lane": LANES["target"],
                     "label": f"Deadline: {metric_label(f.metric)} {f.value:,.0f} {UNIT_SHORT.get(f.unit, f.unit)}",
                     "value": f.value,
                     "unit": f.unit, "fact_id": f.id, "source": sources[f.source_id].title if f.source_id in sources else "",
                     "url": sources[f.source_id].url if f.source_id in sources else "", "page": f.page,
                     "status": f.status.value})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


def events_log_df(store: Store, run_id: str) -> pd.DataFrame:
    return pd.DataFrame([{"time": e.ts, "round": e.round, "stage": e.stage, "level": e.level, "message": e.message}
                         for e in store.events(run_id)])


# ---- links -------------------------------------------------------------------------------------------

def web_url(url: str, page=None) -> str | None:
    """Openable web link for a source, or None for synthetic / uploaded / local documents.
    PDF links jump to the cited page (#page=N works in Chrome, Edge and Firefox viewers)."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    try:
        p = int(float(page)) if page is not None and str(page) not in ("", "nan", "None") else None
    except (TypeError, ValueError):
        p = None
    if p and url.lower().split("?")[0].endswith(".pdf") and "#" not in url:
        return f"{url}#page={p}"
    return url


def source_origin(url: str) -> str:
    u = (url or "").lower()
    if u.startswith("synthetic://"):
        return "Synthetic demo document (not on the internet)"
    if u.startswith("upload://"):
        return "Uploaded document"
    if u.startswith("file://"):
        return "Local file"
    return "Web source"


def document_pages(store: Store, source_id: str) -> list[tuple[int, str]]:
    return store.pages(source_id)


# ---- Overview dashboard ------------------------------------------------------------------------------
# Every value below is computed from stored facts / findings. Nothing is estimated when data is missing.

from .metrics import SOURCE_CAPACITY  # noqa: E402
from .schema import DocType, HypothesisStatus as _HS, Strength  # noqa: E402

DOC_TYPE_LABEL = {
    "annual_report": "Annual reports", "quarterly_results": "Quarterly results",
    "investor_presentation": "Investor presentations", "exchange_filing": "Exchange filings",
    "announcement": "Announcements", "rating_report": "Rating reports", "industry": "Industry sources",
    "news": "News and research", "other": "Other documents",
}


def series_points(store: Store, run_id: str, metric: str, periodicity: str = "annual") -> list[dict]:
    ctx = context(store, run_id)
    return [{"period": p.period, "value": p.value, "unit": p.unit, "fact_id": p.fact_id}
            for p in ctx.series(metric, periodicity).points]


def capacity_points(store: Store, run_id: str) -> tuple[str, list[dict]]:
    """Best available capacity series: installed > renewable > sum of reported sources (same periods only)."""
    for m in ("installed_capacity_mw", "renewable_capacity_mw"):
        pts = series_points(store, run_id, m)
        if pts:
            return metric_label(m), pts
    ctx = context(store, run_id)
    by_period: dict[str, float] = {}
    counts: dict[str, int] = {}
    for m in SOURCE_CAPACITY:
        for p in ctx.series(m).points:
            by_period[p.period] = by_period.get(p.period, 0) + p.value
            counts[p.period] = counts.get(p.period, 0) + 1
    if not counts:
        return "Capacity", []
    full = max(counts.values())
    pts = [{"period": k, "value": v, "unit": "MW", "fact_id": ""} for k, v in by_period.items() if counts[k] == full]
    return "Capacity (sum of reported sources)", sorted(pts, key=lambda x: period_sort_key(x["period"]))


def risk_level(store: Store, run_id: str) -> dict:
    """Rule-based risk signal level from verified findings (not an ESG or credit rating).
    score = sum of rank scores of risk findings that are Supported (full weight) or Unresolved (half weight)."""
    hyps = store.hypotheses(run_id)
    risks = [h for h in hyps if h.direction == "risk"]
    score = sum(h.score for h in risks if h.status == _HS.supported) + \
        0.5 * sum(h.score for h in risks if h.status in (_HS.unresolved, _HS.proposed))
    score5 = round(min(5.0, score), 1)
    if not hyps:
        level = "Insufficient evidence"
    elif score5 >= 3:
        level = "High"
    elif score5 >= 1.2:
        level = "Medium"
    else:
        level = "Low"
    return {"level": level, "score": score5, "n_supported": sum(1 for h in risks if h.status == _HS.supported),
            "n_unresolved": sum(1 for h in risks if h.status in (_HS.unresolved, _HS.proposed))}


def research_progress(store: Store, run_id: str) -> list[dict]:
    run = store.get_run(run_id)
    srcs = store.sources(run_id)
    facts = store.facts(run_id)
    mods = store.module_results(run_id)
    hyps = store.hypotheses(run_id)
    ok = sum(1 for s in srcs if s.fetch_status == "ok")
    with_data = sum(1 for m in mods.values() if m["status"] in ("ok", "partial"))
    checked = sum(1 for h in hyps if h.counter_searched or h.status != _HS.proposed)
    resolved = bool(run and run.company and "UNREGISTERED" not in (run.company.resolution_note or ""))
    return [
        {"step": "Company identified", "value": "verified" if resolved else "unverified", "done": True},
        {"step": "Documents retrieved and read", "value": f"{ok}/{len(srcs)}", "done": ok > 0},
        {"step": "Facts extracted and validated", "value": f"{len(facts)} facts", "done": len(facts) > 0},
        {"step": "Analysis across six modules", "value": f"{with_data}/6 with data", "done": with_data > 0},
        {"step": "Counter-evidence and contradiction checks", "value": f"{checked}/{len(hyps)} findings",
         "done": bool(hyps) and checked == len(hyps)},
    ]


def sources_by_type(store: Store, run_id: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for s in store.sources(run_id):
        if s.fetch_status == "ok":
            counts[s.doc_type.value] = counts.get(s.doc_type.value, 0) + 1
    order = list(DOC_TYPE_LABEL)
    return [(DOC_TYPE_LABEL[k], counts[k]) for k in sorted(counts, key=order.index)]


def highlights(store: Store, run_id: str) -> dict:
    hyps = store.hypotheses(run_id)
    return {
        "opportunities": sum(1 for h in hyps if h.direction == "opportunity" and h.status == _HS.supported),
        "insights": sum(1 for h in hyps if h.status == _HS.supported),
        "risks": sum(1 for h in hyps if h.direction == "risk" and h.status in (_HS.supported, _HS.unresolved)),
        "contradictions": len(contradictions(store, run_id)),
    }


def evidence_confidence(store: Store, run_id: str) -> dict:
    """Share of live (not rejected) findings backed by strong or moderate evidence."""
    live = [h for h in store.hypotheses(run_id) if h.status != _HS.rejected]
    n = {s: sum(1 for h in live if h.strength == s) for s in Strength}
    good = n[Strength.strong] + n[Strength.moderate]
    return {"pct": round(100 * good / len(live)) if live else None, "strong": n[Strength.strong],
            "moderate": n[Strength.moderate], "weak": n[Strength.weak] + n[Strength.insufficient], "total": len(live)}


def outlook(store: Store, run_id: str) -> dict:
    """Deterministic summary of supported findings. A description of the evidence, not a forecast."""
    hyps = store.hypotheses(run_id)
    sup = [h for h in hyps if h.status == _HS.supported]
    risk = sum(h.score for h in sup if h.direction == "risk")
    opp = sum(h.score for h in sup if h.direction == "opportunity")
    unresolved = sum(1 for h in hyps if h.status in (_HS.unresolved, _HS.proposed))
    if len(sup) < 2:
        label, tone = "Insufficient evidence", "neutral"
    elif opp > risk * 1.5:
        label, tone = "Positive", "good"
    elif opp > risk:
        label, tone = "Moderately positive", "good"
    elif risk > opp * 1.5:
        label, tone = "Cautious", "bad"
    else:
        label, tone = "Balanced", "warn"
    top_r = next((h.title for h in sup if h.direction == "risk"), None)
    top_o = next((h.title for h in sup if h.direction == "opportunity"), None)
    parts = []
    if top_o:
        parts.append(f"Main supported opportunity: {top_o}.")
    if top_r:
        parts.append(f"Main supported risk: {top_r}.")
    if unresolved:
        parts.append(f"{unresolved} finding(s) remain unresolved.")
    if not parts:
        parts.append("Not enough supported findings to summarise.")
    return {"label": label, "tone": tone, "text": " ".join(parts)}


def trend(store: Store, run_id: str, metric: str) -> list[dict]:
    """Annual values with year-on-year growth (None where the base is missing, zero or negative)."""
    pts = series_points(store, run_id, metric) if metric != "_capacity" else capacity_points(store, run_id)[1]
    out = []
    for i, p in enumerate(pts):
        prev = pts[i - 1]["value"] if i else None
        yoy = (p["value"] - prev) / prev * 100 if prev and prev > 0 else None
        out.append({**p, "yoy": yoy})
    return out


def energy_mix(store: Store, run_id: str) -> dict:
    """Latest period where capacity by source is reported. Shares are of the reported total only."""
    ctx = context(store, run_id)
    per: dict[str, dict[str, float]] = {}
    for m, (lab, _) in SOURCE_CAPACITY.items():
        for p in ctx.series(m).points:
            per.setdefault(p.period, {})[lab] = p.value
        if not ctx.series(m).points:  # undated statements ("Solar: 1,092 MWp operational")
            fs = [f for f in ctx.facts if f.metric == m and f.value is not None and f.fact_type.value == "reported"]
            if fs:
                per.setdefault("latest disclosed", {})[lab] = max(fs, key=lambda f: f.confidence).value
    if not per:
        return {"period": None, "items": [], "total": 0}
    period = max(per, key=lambda k: (len(per[k]), period_sort_key(k) if k.startswith(("FY", "Q")) else (0, 0)))
    items = sorted(per[period].items(), key=lambda x: -x[1])
    total = sum(v for _, v in items)
    return {"period": period, "total": total,
            "items": [{"source": k, "mw": v, "share": v / total * 100 if total else 0} for k, v in items]}


def esg_series(store: Store, run_id: str) -> dict:
    intensity = series_points(store, run_id, "emission_intensity")
    change = None
    if len(intensity) >= 2 and intensity[0]["value"]:
        change = (intensity[-1]["value"] - intensity[0]["value"]) / intensity[0]["value"] * 100
    ren = {p["period"]: p["value"] for p in series_points(store, run_id, "renewable_capacity_mw")}
    inst = {p["period"]: p["value"] for p in series_points(store, run_id, "installed_capacity_mw")}
    share = [{"period": k, "value": ren[k] / inst[k] * 100} for k in sorted(set(ren) & set(inst), key=period_sort_key)
             if inst[k]]
    if not share:  # from capacity by source: (solar + wind + hydro) / reported total
        ctx = context(store, run_id)
        tot: dict[str, float] = {}
        re_: dict[str, float] = {}
        n: dict[str, int] = {}
        for m, (lab, _) in SOURCE_CAPACITY.items():
            for p in ctx.series(m).points:
                tot[p.period] = tot.get(p.period, 0) + p.value
                n[p.period] = n.get(p.period, 0) + 1
                if lab in ("Solar", "Wind", "Hydro"):
                    re_[p.period] = re_.get(p.period, 0) + p.value
        if n:
            full = max(n.values())
            share = [{"period": k, "value": re_.get(k, 0) / tot[k] * 100} for k in sorted(tot, key=period_sort_key)
                     if n[k] == full and tot[k]]
    # a share above 100% means the two capacities come from different scopes (e.g. group vs listed entity
    # or a target vs an actual); such a ratio is not meaningful, so it is not shown
    share = [p for p in share if 0 <= p["value"] <= 100]
    return {"intensity": intensity, "intensity_change_pct": change, "renewable_share": share}


def recent_developments(store: Store, run_id: str, limit: int = 8) -> list[dict]:
    df = timeline_df(store, run_id)
    if df.empty:
        return []
    d = df[df["lane"].isin(["Milestone / announcement", "Financing", "Promise / target"])]
    d = d[~d["label"].str.startswith("Deadline:")]
    return d.sort_values("date", ascending=False).head(limit).to_dict("records")


def key_metrics_table(store: Store, run_id: str) -> pd.DataFrame:
    ctx = context(store, run_id)
    rows = []
    for m, md in METRICS.items():
        s = ctx.series(m)
        if not len(s):
            continue
        last = s.points[-1]
        prev = s.points[-2] if len(s) > 1 else None
        yoy = (last.value - prev.value) / prev.value * 100 if prev and prev.value and prev.value > 0 else None
        rows.append({"Metric": md.label, "Latest": last.value, "Unit": last.unit, "Period": last.period,
                     "Previous": prev.value if prev else None, "YoY %": yoy, "Periods": len(s),
                     "Conflicts": len(s.conflicts)})
    return pd.DataFrame(rows)


# ---- market-style overview panels -----------------------------------------------------------------

def operational_metrics(store: Store, run_id: str) -> dict:
    cap_label, cap = capacity_points(store, run_id)
    mix = energy_mix(store, run_id)
    uc = series_points(store, run_id, "capacity_under_construction_mw")
    if not uc:  # point-in-time disclosures without a fiscal period
        fs = [f for f in store.facts(run_id) if f.metric == "capacity_under_construction_mw" and f.value is not None
              and f.fact_type.value == "reported"]
        if fs:
            best = max(fs, key=lambda f: (f.period_end or "", f.confidence))
            uc = [{"period": best.period or "latest disclosed", "value": best.value, "unit": "MW", "fact_id": best.id}]
    gen = trend(store, run_id, "generation_mu")
    return {"capacity": cap[-1] if cap else None, "capacity_label": cap_label, "mix": mix,
            "under_construction": uc[-1] if uc else None, "generation": gen[-1] if gen else None}


def balance_ratios(store: Store, run_id: str) -> list[dict]:
    """Latest-period ratios computed from the same period's figures (period mismatches are never mixed)."""
    ctx = context(store, run_id)
    S = {m: {p.period: p.value for p in ctx.series(m).points}
         for m in ("gross_debt_cr", "net_debt_cr", "equity_cr", "ebitda_cr", "finance_cost_cr")}
    out = []

    def latest_common(a: str, b: str):
        common = sorted(set(S[a]) & set(S[b]), key=period_sort_key)
        return common[-1] if common else None

    debt = "net_debt_cr" if S["net_debt_cr"] else "gross_debt_cr"
    p = latest_common(debt, "equity_cr")
    out.append({"label": "Debt / equity", "value": S[debt][p] / S["equity_cr"][p] if p and S["equity_cr"][p] else None,
                "unit": "x", "period": p, "note": f"{metric_label(debt)} ÷ net worth"})
    p = latest_common(debt, "ebitda_cr")
    out.append({"label": f"{'Net' if debt == 'net_debt_cr' else 'Gross'} debt / EBITDA",
                "value": S[debt][p] / S["ebitda_cr"][p] if p and S["ebitda_cr"][p] else None, "unit": "x", "period": p,
                "note": "below 5x is usually comfortable for power companies"})
    p = latest_common("ebitda_cr", "finance_cost_cr")
    out.append({"label": "Interest coverage",
                "value": S["ebitda_cr"][p] / S["finance_cost_cr"][p] if p and S["finance_cost_cr"][p] else None,
                "unit": "x", "period": p, "note": "EBITDA ÷ finance costs"})
    return out


def verdict(store: Store, run_id: str) -> dict:
    hyps = store.hypotheses(run_id)
    return {"risk": sum(1 for h in hyps if h.direction == "risk" and h.status == _HS.supported),
            "opportunity": sum(1 for h in hyps if h.direction == "opportunity" and h.status == _HS.supported),
            "open": sum(1 for h in hyps if h.status in (_HS.unresolved, _HS.weakened, _HS.proposed)),
            "rejected": sum(1 for h in hyps if h.status == _HS.rejected), "total": len(hyps)}


# State and UT centroids (approximate, for map markers). Generic geography, not company data.
INDIA_STATES = {
    "Andhra Pradesh": (15.9, 79.7), "Arunachal Pradesh": (28.2, 94.7), "Assam": (26.2, 92.9), "Bihar": (25.1, 85.3),
    "Chhattisgarh": (21.3, 81.9), "Goa": (15.3, 74.1), "Gujarat": (22.3, 71.2), "Haryana": (29.1, 76.1),
    "Himachal Pradesh": (31.9, 77.2), "Jharkhand": (23.6, 85.3), "Karnataka": (15.3, 75.7), "Kerala": (10.5, 76.3),
    "Madhya Pradesh": (23.5, 78.6), "Maharashtra": (19.6, 75.7), "Manipur": (24.7, 93.9), "Meghalaya": (25.5, 91.4),
    "Mizoram": (23.2, 92.9), "Nagaland": (26.2, 94.6), "Odisha": (20.9, 85.1), "Punjab": (31.1, 75.3),
    "Rajasthan": (27.0, 74.2), "Sikkim": (27.5, 88.5), "Tamil Nadu": (11.1, 78.7), "Telangana": (18.1, 79.0),
    "Tripura": (23.9, 91.9), "Uttar Pradesh": (26.8, 80.9), "Uttarakhand": (30.1, 79.0), "West Bengal": (22.9, 87.9),
    "Jammu and Kashmir": (33.8, 75.0), "Ladakh": (34.2, 77.6), "Delhi": (28.7, 77.1),
    "Andaman and Nicobar": (11.7, 92.7), "Puducherry": (11.9, 79.8),
}
_STATE_RX = {s: re.compile(r"\b" + s.replace(" and ", r"\s+(?:and|&)\s+").replace(" ", r"\s+") + r"\b", re.I)
             for s in INDIA_STATES}
_STATE_RX["Odisha"] = re.compile(r"\b(Odisha|Orissa)\b", re.I)
_PROJECT_CATS = ("commissioning", "award", "ppa", "delay", "acquisition", "curtailment")


def project_locations(store: Store, run_id: str) -> list[dict]:
    """States named in project disclosures (events, pipeline and target passages), with MW where stated."""
    out: dict[str, dict] = {}
    for f in store.facts(run_id):
        if not ((f.fact_type.value == "event" and f.event_category in _PROJECT_CATS) or
                f.metric in ("capacity_under_construction_mw", "renewable_target_mw", "capacity_target_mw")):
            continue
        for state, rx in _STATE_RX.items():
            if rx.search(f.passage):
                d = out.setdefault(state, {"state": state, "mentions": 0, "mw": 0.0, "examples": [], "fact_ids": [],
                                           "lat": INDIA_STATES[state][0], "lon": INDIA_STATES[state][1],
                                           "kinds": set()})
                d["mentions"] += 1
                d["mw"] += (f.value or 0) if f.unit == "MW" else 0
                d["kinds"].add(f.event_category or "pipeline")
                d["fact_ids"].append(f.id)
                if len(d["examples"]) < 2:
                    d["examples"].append(f.passage[:140])
    rows = sorted(out.values(), key=lambda d: -d["mentions"])
    for d in rows:
        d["kinds"] = sorted(d["kinds"])
        d["status"] = "Operating" if d["kinds"] == ["commissioning"] else \
            "Issue reported" if {"delay", "curtailment"} & set(d["kinds"]) else "Upcoming / mixed"
    return rows


_MW_RX = re.compile(r"(\d[\d,]*\.?\d*)\s*(GW|MW)p?\b", re.I)


def upcoming_projects(store: Store, run_id: str, limit: int = 8) -> list[dict]:
    """Pipeline items: awards, PPAs, delays, planned commissioning and capacity under construction."""
    rows = []
    for f in store.facts(run_id):
        is_pipe = f.metric == "capacity_under_construction_mw" and f.fact_type.value == "reported"
        is_event = f.fact_type.value == "event" and f.event_category in ("award", "ppa", "delay", "acquisition")
        if not (is_pipe or is_event):
            continue
        mw = f.value if f.unit == "MW" and f.value else None
        if mw is None:
            m = _MW_RX.search(f.passage)
            if m:
                v = float(m.group(1).replace(",", ""))
                mw = v * 1000 if m.group(2).upper() == "GW" else v
        status = {"award": "Won / awarded", "ppa": "PPA signed", "delay": "Delayed", "acquisition": "Acquisition"}.get(
            f.event_category, "Under construction")
        rows.append({"item": re.sub(r"\s+", " ", f.passage)[:120], "mw": mw, "status": status,
                     "date": f.period_end or (period_end(f.period) if f.period else None), "fact_id": f.id,
                     "source_id": f.source_id, "page": f.page, "passage": f.passage})
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    return rows[:limit]


def financial_overview(store: Store, run_id: str) -> dict:
    return {lab: trend(store, run_id, m) for lab, m in (("Revenue", "revenue_cr"), ("EBITDA", "ebitda_cr"),
                                                         ("PAT", "pat_cr"))}
