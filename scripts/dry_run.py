"""Finals rehearsal: run the agent on every NIFTY 50 Track B company, time it, and flag anything odd.

    python scripts/dry_run.py                       # NTPC, POWERGRID, ONGC, COALINDIA, RELIANCE
    python scripts/dry_run.py NTPC TATAPOWER        # any listed energy companies
    python scripts/dry_run.py --rounds 2            # faster
    python scripts/dry_run.py --core                # 20 large listed energy companies (~15 min)
    python scripts/dry_run.py --all                 # every energy company in data/companies.csv (~30 min)

Writes dry_run/<date>/report.md (read it) and dry_run/<date>.zip (send it back for diagnosis: it holds
only the extracted facts behind each finding, calculations and the run log, not the source PDFs).
Each run is also saved in the app's database, so the results open in the dashboard afterwards.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eia.agent import ResearchAgent  # noqa: E402
from eia.config import get_settings  # noqa: E402
from eia.db import Store  # noqa: E402
from eia import discovery, views  # noqa: E402
from eia.identity import resolve  # noqa: E402
from eia.periods import period_sort_key  # noqa: E402

TRACK_B_NIFTY50 = ["NTPC", "POWERGRID", "ONGC", "COALINDIA", "RELIANCE"]
# large listed energy companies across every business type (power, grid, oil, gas, coal, renewables, finance, kit)
CORE = ["NTPC", "POWERGRID", "ONGC", "COALINDIA", "RELIANCE", "IOC", "BPCL", "HINDPETRO", "GAIL", "OIL", "NHPC",
        "SJVN", "TATAPOWER", "ADANIGREEN", "ADANIPOWER", "JSWENERGY", "TORNTPOWER", "NLCINDIA", "PETRONET", "PFC"]


def anomalies(store: Store, rid: str) -> list[str]:
    """Things a judge would notice: implausible growth, very old periods, odd shares, thin evidence."""
    out = []
    for c in store.calculations(rid):
        if c.result is None:
            continue
        if c.unit == "%" and ("YoY" in c.name or "CAGR" in c.name) and abs(c.result) > 150:
            out.append(f"Large growth figure: {c.name} = {c.result:,.1f}% ({c.period}) [{c.module}]")
        if "share" in c.name.lower() and c.unit == "%" and not 0 <= c.result <= 100:
            out.append(f"Share outside 0-100%: {c.name} = {c.result:,.1f}%")
    years = [period_sort_key(f.period)[0] for f in store.facts(rid) if f.period and f.metric != "event"]
    if years:
        latest = max(years)
        old = sorted({y for y in years if y < latest - 10})
        if old:
            out.append(f"Facts dated more than 10 years before the latest ({latest}): {old[:6]} (held out of trends)")
    for key, m in store.module_results(rid).items():
        for n in m.get("notes", []):
            if "held out" in n or "not used in trends" in n:
                out.append(f"[{m.get('name', key)}] {n}")
    for key, m in store.module_results(rid).items():
        for n in m.get("notes", []):
            if any(k in n for k in ("not physically", "plausible range", "different documents", "different entities",
                                    "exceeds installed")):
                out.append(f"[{m.get('name', key)}] guard: {n}")
    from eia.views import context
    ctx = context(store, rid)
    for metric in ("revenue_cr", "ebitda_cr", "pat_cr", "gross_debt_cr", "installed_capacity_mw", "generation_mu"):
        for w in ctx.series(metric).warnings:
            if "mixes consolidated and standalone" in w:
                out.append(f"Scope mix: {w}")
    ren, inst = ctx.series("renewable_capacity_mw"), ctx.series("installed_capacity_mw")
    for p in [x for x in ren.periods if inst.get(x)]:
        if ren.get(p).value > inst.get(p).value * 1.001:
            out.append(f"Renewable capacity {ren.get(p).value:,.0f} MW > installed {inst.get(p).value:,.0f} MW in {p}")
    for h in store.hypotheses(rid):
        big = [float(x.replace(",", "")) for x in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s?(?:%|pp)", h.statement)]
        if any(v > 300 for v in big):
            out.append(f"Finding quotes a percentage above 300: '{h.title}' ({h.status.value})")
    return list(dict.fromkeys(out))


def summarise(store: Store, rid: str, seconds: float) -> dict:
    s = views.run_summary(store, rid)
    b = discovery.build(store, rid)
    mods = store.module_results(rid)
    peers = store.peers(rid)
    return {
        "company": s["company"].name, "nse": s["company"].nse, "run_id": rid, "seconds": round(seconds),
        "status": s["run"].status, "sources_ok": s["sources_ok"], "sources_failed": s["sources_failed"],
        "facts": s["facts"], "facts_verified": s["facts_verified"], "findings": s["hypotheses"],
        "by_status": s["by_status"],
        "modules": {m.get("name", k): m.get("status") for k, m in mods.items()},
        "discovery": None if not b else {"title": b["title"], "sentence": b["discovery"], "status": b["status"],
                                         "strength": b["strength"], "sources": b["n_sources"],
                                         "cross_document": b["non_obvious"],
                                         "peer_check": (b["peer_check"] or {}).get("note")},
        "peers": [{"name": p["name"], "ok": not p["error"], "error": p["error"]} for p in peers],
        "failed_sources": [f"{x.title or x.url}: {x.error}" for x in store.sources(rid) if x.fetch_status == "failed"][:8],
        "errors": [e.message[:200] for e in store.events(rid) if e.level == "error"][:8],
        "anomalies": anomalies(store, rid),
    }


def markdown(rows: list[dict]) -> str:
    L = [f"# Dry run, {datetime.now():%d %b %Y %H:%M}", "",
         "| Company | Time | Sources (ok/failed) | Facts | Findings | Discovery | Peers | Anomalies |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['query']} | — | — | — | — | **FAILED: {r['error']}** | — | — |")
            continue
        d = r["discovery"]
        L.append(f"| {r['company']} | {r['seconds']}s | {r['sources_ok']}/{r['sources_failed']} | {r['facts']} | "
                 f"{r['findings']} | {(d['status'] + ', ' + d['strength']) if d else 'none'} | "
                 f"{sum(p['ok'] for p in r['peers'])}/{len(r['peers'])} | {len(r['anomalies'])} |")
    for r in rows:
        if "error" in r:
            continue
        d = r["discovery"]
        L += ["", f"## {r['company']} ({r['nse']}): {r['seconds']} s, status {r['status']}", "",
              f"**Discovery:** {d['sentence'] if d else 'none'}" +
              (f"  \n_{d['title']} · {d['status']} · {d['strength']} · {d['sources']} source(s)"
               f"{' · cross-document' if d and d['cross_document'] else ''}_" if d else ""),
              "", f"Findings by status: {r['by_status']}", "",
              "Modules: " + ", ".join(f"{k}: {v}" for k, v in r["modules"].items())]
        if d and d.get("peer_check"):
            L += ["", f"Peer check: {d['peer_check']}"]
        if r["peers"]:
            L += ["", "Peers: " + ", ".join(p["name"] + ("" if p["ok"] else f" (unavailable: {p['error']})") for p in r["peers"])]
        for title, items in (("Anomalies to look at", r["anomalies"]), ("Failed sources", r["failed_sources"]),
                             ("Errors", r["errors"])):
            if items:
                L += ["", f"**{title}**", ""] + [f"- {x}" for x in items]
    return "\n".join(L) + "\n"


def bundle(store: Store, rid: str, z: zipfile.ZipFile, tag: str) -> None:
    """Small diagnostic files: facts used by findings, calculations, module results, run log."""
    import pandas as pd
    used = {i for h in store.hypotheses(rid) for i in h.supporting_fact_ids + h.counter_fact_ids}
    calcs = store.calculations(rid)
    used |= {i for c in calcs for i in store.calc_input_facts(c.id)}
    facts = [f for f in store.facts(rid) if f.id in used]
    srcs = {s.id: s for s in store.sources(rid)}
    z.writestr(f"{tag}/facts_used.csv", pd.DataFrame([{
        "id": f.id, "metric": f.metric, "value": f.value, "unit": f.unit, "raw": f"{f.raw_value} {f.raw_unit}",
        "period": f.period, "inferred": f.period_inferred, "scope": f.scope.value, "type": f.fact_type.value,
        "status": f.status.value, "page": f.page, "source": srcs[f.source_id].title if f.source_id in srcs else "",
        "url": srcs[f.source_id].url if f.source_id in srcs else "", "passage": f.passage[:400]} for f in facts]).to_csv(index=False))
    z.writestr(f"{tag}/calculations.csv", pd.DataFrame([{
        "module": c.module, "name": c.name, "result": c.result, "unit": c.unit, "period": c.period, "status": c.status,
        "inputs": json.dumps(c.inputs, default=str), "formula": c.formula} for c in calcs]).to_csv(index=False))
    z.writestr(f"{tag}/findings.json", json.dumps([h.model_dump(mode="json") for h in store.hypotheses(rid)], indent=1))
    z.writestr(f"{tag}/modules.json", json.dumps(store.module_results(rid), indent=1, default=str))
    z.writestr(f"{tag}/peers.json", json.dumps(store.peers(rid), indent=1, default=str))
    z.writestr(f"{tag}/log.txt", "\n".join(f"[R{e.round} {e.stage} {e.level}] {e.message}" for e in store.events(rid)))
    z.writestr(f"{tag}/sources.csv", views.sources_df(store, rid).to_csv(index=False))
    # what the charts and KPI cards show: the selected point per period, with where it came from
    from eia.metrics import METRICS
    ctx = views.context(store, rid)
    rows = []
    for m in METRICS:
        for per in ("annual", "quarterly"):
            ser = ctx.series(m, per)
            for pt in ser.points:
                f = ctx.facts_by_id.get(pt.fact_id)
                src = srcs.get(f.source_id) if f else None
                rows.append({"metric": m, "periodicity": per, "period": pt.period, "value": pt.value, "unit": pt.unit,
                             "scope": pt.scope, "raw": f"{f.raw_value} {f.raw_unit}" if f else "",
                             "source": src.title if src else "", "page": f.page if f else "",
                             "passage": (f.passage[:300] if f else "")})
            for ex in ser.excluded:
                rows.append({"metric": m, "periodicity": per, "period": ex["period"], "value": ex["value"], "unit": "",
                             "scope": "HELD OUT", "raw": "", "source": "", "page": "", "passage": ex["reason"][:300]})
    z.writestr(f"{tag}/series.csv", pd.DataFrame(rows).to_csv(index=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("companies", nargs="*", default=TRACK_B_NIFTY50)
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--core", action="store_true", help="20 large listed energy companies")
    ap.add_argument("--all", action="store_true", help="every energy company in the registry")
    a = ap.parse_args()
    if a.all:
        from eia.identity import load_registry
        a.companies = [c.nse for c in load_registry() if c.nse and not (c.segment or "").startswith("non-energy")]
    elif a.core:
        a.companies = CORE
    s = get_settings()
    store = Store(s.db_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = ROOT / "dry_run" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    zpath = ROOT / "dry_run" / f"{stamp}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for q in a.companies:
            res = resolve(q)
            if res.status != "resolved":
                rows.append({"query": q, "error": res.message or res.status})
                print(f"\n=== {q}: could not resolve ({res.status})")
                continue
            print(f"\n=== {res.company.name} ({res.company.nse})")
            t0 = time.time()
            last = [0.0]

            def log(stage, msg, frac):
                if time.time() - last[0] > 0.5 or stage in ("peers", "verify"):
                    print(f"  [{time.time() - t0:5.0f}s {stage:8}] {msg[:140]}")
                    last[0] = time.time()
            try:
                out = ResearchAgent(store, s, progress=log).research(res.company, "live", max_rounds=a.rounds)
            except Exception as e:
                rows.append({"query": q, "error": f"{type(e).__name__}: {e}"})
                continue
            r = summarise(store, out.run_id, time.time() - t0)
            rows.append(r)
            d = r["discovery"]
            print(f"  -> {r['seconds']} s, {r['facts']} facts, {r['findings']} findings; discovery: "
                  f"{d['title'] + ' (' + d['status'] + ')' if d else 'none'}; {len(r['anomalies'])} anomaly(ies)")
            bundle(store, out.run_id, z, re.sub(r"\W+", "_", res.company.nse or q))
        md = markdown(rows)
        z.writestr("report.md", md)
        z.writestr("summary.json", json.dumps(rows, indent=1, default=str))
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    print(f"\nReport: {out_dir / 'report.md'}\nSend this file back for diagnosis: {zpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
