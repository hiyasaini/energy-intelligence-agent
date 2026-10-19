"""Research report export (Markdown and standalone HTML). Every finding carries its Evidence Passport."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .db import Store
from .modules import MODULE_ORDER
from .views import contradictions, passport, run_summary, source_origin, sources_df, web_url

DISCLAIMER = ("Automated research output. Findings are hypotheses graded by evidence strength, not investment advice. "
              "Correlation and chronology are never treated as causation. Verify against the cited sources.")


def _fmt(v, unit=""):
    if v is None:
        return "n/a"
    u = {"INR_cr": " ₹ cr", "MW": " MW", "MU": " MU", "%": "%", "x": "x"}.get(unit, f" {unit}" if unit else "")
    return f"{v:,.0f}{u}" if abs(v) >= 1000 else f"{v:,.2f}{u}"


def _src_ref(row: dict) -> str:
    page = f", p.{row['page']}" if row.get("page") else ""
    title = (row["source_title"] or row["source_url"]).replace("[", "(").replace("]", ")")
    url = web_url(row["source_url"], row.get("page"))
    if url:
        return f"[{title}]({url}){page}"
    return f"{title}{page} _({source_origin(row['source_url']).lower()})_"


def _a(url: str, text: str, page=None) -> str:
    """HTML link only for real web sources; offline documents are labelled instead of linked."""
    u = web_url(url, page)
    if u:
        return f"<a href='{_e(u)}' target='_blank' rel='noopener'>{_e(text)}</a>"
    return f"{_e(text)} <span class='muted'>({_e(source_origin(url).lower())})</span>"


def build_markdown(store: Store, run_id: str, max_findings: int = 25) -> str:
    s = run_summary(store, run_id)
    run, co = s["run"], s["company"]
    L: list[str] = []
    if s["mode"] == "demo":
        L += ["> **DEMO MODE — SYNTHETIC DATA.** The company, documents and figures below are invented to demonstrate "
              "the pipeline. They do not describe any real company.", ""]
    L += [f"# Energy Intelligence Report: {co.name}", "",
          f"- **Identifiers:** NSE `{co.nse or 'n/a'}`" + (f", BSE `{co.bse}`" if co.bse else "") +
          (f" · segment: {co.segment}" if co.segment else ""),
          f"- **Identity resolution:** {co.resolution_note or 'n/a'}",
          f"- **Run:** `{run.id}` · mode **{run.mode}** · status **{run.status}** · rounds {run.rounds_completed} · "
          f"started {run.started_at} · finished {run.finished_at or 'n/a'}",
          f"- **Providers:** search `{run.settings.get('search_provider')}`, LLM `{run.settings.get('llm_provider')}`",
          f"- **Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
          f"_{DISCLAIMER}_", "", "## Discovery summary", "",
          f"- Sources parsed: **{s['sources_ok']}** of {s['sources_total']} attempted ({s['sources_failed']} failed)",
          f"- Facts extracted: **{s['facts']}** ({s['facts_verified']} verified verbatim in their source passage); "
          f"{s['targets']} targets, {s['events']} dated events",
          f"- Periods covered: {', '.join(s['periods_covered']) or 'none'}",
          f"- Findings: **{s['hypotheses']}** — " + ", ".join(f"{k}: {v}" for k, v in sorted(s['by_status'].items())), "",
          "**Evidence labels.** *Verified fact*: value found verbatim in the cited passage. *Unverified claim*: extracted "
          "but not located verbatim. *Calculated*: deterministic Python over cited facts. *Hypothesis*: a claim under "
          "test. *Interpretation*: narrative only, never a source of numbers.", ""]

    mods = store.module_results(run_id)
    L += ["## Module overview", "", "| Module | Status | Summary | Missing data |", "|---|---|---|---|"]
    for key, name in MODULE_ORDER:
        m = mods.get(key, {})
        L.append(f"| {name} | {m.get('status', 'not run')} | {m.get('summary', '').replace('|', '/')} | "
                 f"{', '.join(m.get('missing', [])) or '—'} |")
    L.append("")

    hyps = store.hypotheses(run_id)[:max_findings]
    L += ["## Ranked findings with Evidence Passports", ""]
    if not hyps:
        L += ["_No findings: insufficient evidence was collected. See the module overview for missing data._", ""]
    for i, h in enumerate(hyps, 1):
        p = passport(store, run_id, h.id)
        L += [f"### {i}. {h.title}", "",
              f"**Status:** {p['status_label']} · **Evidence strength:** {h.strength.value} · **Direction:** "
              f"{h.direction} · **Module:** {h.module} · **Rank score:** {h.score:.2f}", "",
              f"**Hypothesis.** {h.statement}", ""]
        if p["supporting"]:
            L += ["**Supporting evidence**", "", "| Fact | Value | Period | Label | Source | Passage |", "|---|---|---|---|---|---|"]
            for r in p["supporting"]:
                lab = "verified fact" if r["status"] == "source_verified" else "UNVERIFIED claim"
                per = r["period"] + (" (inferred)" if r["period_inferred"] else "")
                L.append(f"| {r['metric']} | {_fmt(r['value'], r['unit'])} | {per} | {lab} | {_src_ref(r)} | "
                         f"“{r['passage'][:160].replace('|', '/').replace(chr(10), ' ')}” |")
            L.append("")
        if p["calculations"]:
            L += ["**Calculations** (deterministic)", ""]
            for c in p["calculations"]:
                ins = ", ".join(f"{k}={v:,.2f}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in c["inputs"].items())
                L.append(f"- {c['name']}: `{c['formula']}` with {ins or 'no inputs'} → **{_fmt(c['result'], c['unit'])}** "
                         f"[{c['status']}]" + (f" — {c['notes']}" if c['notes'] else ""))
            L.append("")
        if p["counter"]:
            L += ["**Counter-evidence**", ""]
            for r in p["counter"]:
                L.append(f"- {r['metric']} {r['period']}: “{r['passage'][:180]}” — {_src_ref(r)}")
            L.append("")
        L += ["**Counterarguments**", ""] + [f"- {c}" for c in p["counterarguments"]] + [""]
        L += ["**Limitations**", ""] + [f"- {c}" for c in p["limitations"] or ["None recorded."]] + [""]
        L += [f"**Falsification condition.** {h.falsification or 'n/a'}", ""]
        if h.interpretation:
            L += [f"**Interpretation (LLM, number-guarded; not evidence).** {h.interpretation}", ""]
        L += ["**Verification history.** " + " → ".join(h.history), ""]

    cons = contradictions(store, run_id)
    L += ["## Contradictory evidence", ""]
    if not cons:
        L += ["_No conflicting values for the same metric and period were found._", ""]
    for c in cons:
        L.append(f"- **{c['metric']} {c['period']}** differs by {c['rel_diff_pct']}% across sources:")
        for r in c["facts"]:
            sel = " (selected for analysis)" if r["id"] == c["selected_fact_id"] else ""
            L.append(f"  - {_fmt(r['value'], r['unit'])} [{r['scope']}, {r['source_tier']}] — {_src_ref(r)}{sel}")
    L.append("")

    sdf = sources_df(store, run_id)
    L += ["## Sources", "", "| # | Title | Type | Tier | Published | Status | Facts |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(sdf.to_dict("records") if not sdf.empty else [], 1):
        title = (r["title"] or r["url"]).replace("|", "/").replace("[", "(").replace("]", ")")
        link = f"[{title}]({r['url']})" if web_url(r["url"]) else f"{title} _({source_origin(r['url']).lower()})_"
        L.append(f"| {i} | {link} | {r['doc_type']} | {r['tier']} | {r['published'] or '—'} | "
                 f"{r['status']}{(': ' + r['error'][:60]) if r['error'] else ''} | {r['facts']} |")
    L += ["", "## Method and limitations", "",
          "- Facts are extracted with deterministic rules (sentences and tables); optional LLM proposals are kept only "
          "if the quote and number are found verbatim on the page. Units are normalised (MW, MU, ₹ crore) and never guessed.",
          "- Every number in a finding comes from a stored calculation whose input facts are linked in the database.",
          "- Hypotheses are challenged with targeted counter-evidence searches and deterministic counter-checks; "
          f"research is bounded to {run.settings.get('max_rounds', 3)} rounds.",
          "- Missing metrics make the relevant module report insufficient data instead of estimating values.", ""]
    return "\n".join(L)


CSS = """
body{background:#0b1220;color:#dbe4f0;font:15px/1.55 -apple-system,Segoe UI,Inter,Roboto,sans-serif;margin:0}
main{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
h1{color:#f1f5f9;font-size:28px;margin:8px 0 6px} h2{color:#67e8f9;border-bottom:1px solid #1e293b;padding-bottom:6px;margin-top:36px}
h3{color:#f1f5f9;margin-top:28px} a{color:#22d3ee} code{background:#111a2e;padding:1px 5px;border-radius:4px}
table{border-collapse:collapse;width:100%;margin:8px 0 14px;font-size:13px} th,td{border:1px solid #1e293b;padding:6px 8px;vertical-align:top;text-align:left}
th{background:#111a2e;color:#93c5fd} tr:nth-child(even) td{background:#0e1729}
.banner{background:#422006;border:1px solid #f59e0b;color:#fde68a;padding:10px 14px;border-radius:8px;font-weight:600}
.card{background:#0f1a2e;border:1px solid #1e293b;border-radius:10px;padding:14px 18px;margin:14px 0}
.pill{display:inline-block;border-radius:999px;padding:1px 10px;font-size:12px;font-weight:600;margin-right:6px}
.supported{background:#083344;color:#67e8f9}.weakened,.unresolved,.proposed{background:#422006;color:#fbbf24}
.rejected{background:#3f1d1d;color:#fca5a5}.insufficient_evidence{background:#1f2937;color:#cbd5e1}
.muted{color:#94a3b8;font-size:13px} blockquote{border-left:3px solid #f59e0b;margin:0;padding:4px 12px;color:#fde68a}
li{margin:3px 0}
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def build_html(store: Store, run_id: str, max_findings: int = 25) -> str:
    s = run_summary(store, run_id)
    run, co = s["run"], s["company"]
    H: list[str] = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
                    f"content='width=device-width,initial-scale=1'><title>{_e(co.name)} — Energy Intelligence Report</title>"
                    f"<style>{CSS}</style></head><body><main>"]
    if s["mode"] == "demo":
        H.append("<p class='banner'>DEMO MODE — SYNTHETIC DATA. The company, documents and figures are invented to "
                 "demonstrate the pipeline and do not describe any real company.</p>")
    H.append(f"<h1>{_e(co.name)}</h1><p class='muted'>NSE {_e(co.nse or 'n/a')} · {_e(co.segment)} · run {_e(run.id)} · "
             f"mode {_e(run.mode)} · status {_e(run.status)} · {run.rounds_completed} round(s) · search "
             f"{_e(run.settings.get('search_provider'))} · LLM {_e(run.settings.get('llm_provider'))}</p>"
             f"<p class='muted'>{_e(co.resolution_note)}</p><p><em>{_e(DISCLAIMER)}</em></p>")
    H.append("<h2>Discovery summary</h2><ul>"
             f"<li>Sources parsed: <b>{s['sources_ok']}</b> of {s['sources_total']} ({s['sources_failed']} failed)</li>"
             f"<li>Facts: <b>{s['facts']}</b> ({s['facts_verified']} verified verbatim); {s['targets']} targets; "
             f"{s['events']} dated events</li><li>Periods: {_e(', '.join(s['periods_covered']) or 'none')}</li>"
             f"<li>Findings: <b>{s['hypotheses']}</b> — " +
             ", ".join(f"{_e(k)}: {v}" for k, v in sorted(s['by_status'].items())) + "</li></ul>")
    mods = store.module_results(run_id)
    H.append("<h2>Module overview</h2><table><tr><th>Module</th><th>Status</th><th>Summary</th><th>Missing data</th></tr>")
    for key, name in MODULE_ORDER:
        m = mods.get(key, {})
        H.append(f"<tr><td>{_e(name)}</td><td>{_e(m.get('status', 'not run'))}</td><td>{_e(m.get('summary', ''))}</td>"
                 f"<td>{_e(', '.join(m.get('missing', [])) or '—')}</td></tr>")
    H.append("</table><h2>Ranked findings with Evidence Passports</h2>")
    hyps = store.hypotheses(run_id)[:max_findings]
    if not hyps:
        H.append("<p>No findings: insufficient evidence was collected.</p>")
    for i, h in enumerate(hyps, 1):
        p = passport(store, run_id, h.id)
        H.append(f"<div class='card'><h3>{i}. {_e(h.title)}</h3>"
                 f"<span class='pill {h.status.value}'>{_e(p['status_label'])}</span>"
                 f"<span class='pill insufficient_evidence'>strength: {_e(h.strength.value)}</span>"
                 f"<span class='muted'>{_e(h.direction)} · {_e(h.module)} · score {h.score:.2f}</span>"
                 f"<p><b>Hypothesis.</b> {_e(h.statement)}</p>")
        if p["supporting"]:
            H.append("<b>Supporting evidence</b><table><tr><th>Fact</th><th>Value</th><th>Period</th><th>Label</th>"
                     "<th>Source</th><th>Passage</th></tr>")
            for r in p["supporting"]:
                lab = "verified fact" if r["status"] == "source_verified" else "UNVERIFIED claim"
                H.append(f"<tr><td>{_e(r['metric'])}</td><td>{_e(_fmt(r['value'], r['unit']))}</td>"
                         f"<td>{_e(r['period'])}{' (inferred)' if r['period_inferred'] else ''}</td><td>{lab}</td>"
                         f"<td>{_a(r['source_url'], r['source_title'][:60] or r['source_url'][:60], r['page'])}"
                         f"{', p.' + str(r['page']) if r['page'] else ''}</td><td>“{_e(r['passage'][:220])}”</td></tr>")
            H.append("</table>")
        if p["calculations"]:
            H.append("<b>Calculations (deterministic)</b><ul>")
            for c in p["calculations"]:
                ins = ", ".join(f"{k}={v:,.2f}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in c["inputs"].items())
                H.append(f"<li>{_e(c['name'])}: <code>{_e(c['formula'])}</code> with {_e(ins)} → "
                         f"<b>{_e(_fmt(c['result'], c['unit']))}</b> [{_e(c['status'])}] {_e(c['notes'])}</li>")
            H.append("</ul>")
        if p["counter"]:
            H.append("<b>Counter-evidence</b><ul>" + "".join(
                f"<li>{_e(r['metric'])} {_e(r['period'])}: “{_e(r['passage'][:200])}” — "
                f"{_a(r['source_url'], r['source_title'][:60], r['page'])}</li>" for r in p["counter"]) + "</ul>")
        H.append("<b>Counterarguments</b><ul>" + "".join(f"<li>{_e(c)}</li>" for c in p["counterarguments"]) + "</ul>")
        H.append("<b>Limitations</b><ul>" + "".join(f"<li>{_e(c)}</li>" for c in p["limitations"] or ["None recorded."]) +
                 "</ul>")
        H.append(f"<p><b>Falsification condition.</b> {_e(h.falsification or 'n/a')}</p>")
        if h.interpretation:
            H.append(f"<blockquote><b>Interpretation (LLM, number-guarded; not evidence).</b> {_e(h.interpretation)}</blockquote>")
        H.append(f"<p class='muted'>History: {_e(' → '.join(h.history))}</p></div>")
    cons = contradictions(store, run_id)
    H.append("<h2>Contradictory evidence</h2>")
    if not cons:
        H.append("<p>No conflicting values for the same metric and period were found.</p>")
    for c in cons:
        H.append(f"<p><b>{_e(c['metric'])} {_e(c['period'])}</b> differs by {c['rel_diff_pct']}% across sources:</p><ul>")
        for r in c["facts"]:
            sel = " <em>(selected for analysis)</em>" if r["id"] == c["selected_fact_id"] else ""
            H.append(f"<li>{_e(_fmt(r['value'], r['unit']))} [{_e(r['scope'])}, {_e(r['source_tier'])}] — "
                     f"{_a(r['source_url'], r['source_title'][:70], r['page'])}{sel}</li>")
        H.append("</ul>")
    sdf = sources_df(store, run_id)
    H.append("<h2>Sources</h2><table><tr><th>#</th><th>Title</th><th>Type</th><th>Tier</th><th>Published</th>"
             "<th>Status</th><th>Facts</th></tr>")
    for i, r in enumerate(sdf.to_dict("records") if not sdf.empty else [], 1):
        H.append(f"<tr><td>{i}</td><td>{_a(r['url'], r['title'] or r['url'])}</td>"
                 f"<td>{_e(r['doc_type'])}</td><td>{_e(r['tier'])}</td><td>{_e(r['published'] or '—')}</td>"
                 f"<td>{_e(r['status'])} {_e(r['error'][:60])}</td><td>{r['facts']}</td></tr>")
    H.append("</table></main></body></html>")
    return "".join(H)
