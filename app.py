"""Energy Intelligence Agent: Streamlit dashboard.

Launch:  streamlit run app.py
"""
from __future__ import annotations

import re

import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eia import views  # noqa: E402
from eia.agent import ResearchAgent, SeedDocument  # noqa: E402
from eia.config import get_settings  # noqa: E402
from eia.db import Store  # noqa: E402
from eia.demo import run_demo  # noqa: E402
from eia.graph import EDGE_COLORS, build_graph, graph_figure  # noqa: E402
from eia.identity import resolve, unregistered  # noqa: E402
from eia.jobs import JobRegistry  # noqa: E402
from eia.metrics import METRICS, metric_label  # noqa: E402
from eia.modules import MODULE_ORDER  # noqa: E402
from eia.providers.market import NIFTY50, fetch_chart, fetch_quote, relative_performance  # noqa: E402
from eia.report import build_html, build_markdown  # noqa: E402
from eia.schema import RelLabel  # noqa: E402
from eia.verification import status_label  # noqa: E402
from ui.theme import (C_AQUA, C_BLUE, C_GREY, C_ORANGE, AMBER, BLUE, CORAL, CSS, CYAN, GREEN, MUTED, ORANGE, PLOTLY_CONFIG, PLOTLY_LAYOUT,  # noqa: E402
                      SERIES_COLORS, SKYLINE, SOURCE_COLORS, VIOLET, direction_tag, esc, gauge, highlight, minibars,
                      module_chip, nav_css, page_header, ptitle, ring, section, sparkline, stat_strip, status_chip,
                      status_color, strength_chip)

MODULE_PAGES = {"Promise vs Reality": "promise_reality", "Green Growth": "green_growth",
                "Capital & Cash": "capital_cash", "Hidden Risk": "hidden_risk",
                "Hidden Connections": "hidden_connections", "Early Warning": "early_warning"}
PAGES = ["Overview", "Signal Radar", "Discovery Feed", *MODULE_PAGES, "Discovery Graph", "Contradiction Lab",
         "Timeline", "Evidence Explorer", "Report Studio"]
SLUG = {p: p.lower().replace(" & ", "-").replace(" ", "-") for p in PAGES}
FROM_SLUG = {v: k for k, v in SLUG.items()}
PAGE_HELP = {
    "Signal Radar": "Choose a company and run the research agent, or try the synthetic demo.",
    "Discovery Feed": "Every finding, ranked by severity, evidence strength and verification status. Open one to "
                      "audit its Evidence Passport.",
    "Discovery Graph": "How sources, facts, calculations and findings connect. Hover a node for details.",
    "Contradiction Lab": "Where sources disagree, and the evidence for and against each contested finding.",
    "Timeline": "Targets and announcements set against what was later delivered in operations and cash.",
    "Evidence Explorer": "Read the source documents with the cited passage highlighted, and search every extracted fact.",
    "Report Studio": "Download the research report with every finding's evidence and source links.",
    "Promise vs Reality": "Stated targets compared with disclosed outcomes and the historical delivery pace.",
    "Green Growth": "Capacity, generation and revenue trends, and whether they move together.",
    "Capital & Cash": "Capex, debt, finance costs, cash generation and funding capacity.",
    "Hidden Risk": "Independent warning signals combined into a composite view.",
    "Hidden Connections": "Links between events and metrics where the evidence supports them. Never read as causation.",
    "Early Warning": "Trend reversals, sharp decelerations and margin compression.",
}
MODULE_CHARTS = {
    "promise_reality": ["renewable_capacity_mw", "installed_capacity_mw", "capacity_under_construction_mw"],
    "green_growth": ["renewable_capacity_mw", "installed_capacity_mw", "generation_mu", "revenue_cr"],
    "capital_cash": ["capex_cr", "cfo_cr", "gross_debt_cr", "net_debt_cr", "ebitda_cr", "finance_cost_cr"],
    "hidden_risk": ["receivables_cr", "revenue_cr", "cfo_cr"],
    "hidden_connections": ["generation_mu", "revenue_cr", "gross_debt_cr", "finance_cost_cr"],
    "early_warning": ["revenue_cr", "ebitda_cr", "pat_cr", "generation_mu"],
}
TREND_METRICS = {"Revenue": "revenue_cr", "Net profit": "pat_cr", "EBITDA": "ebitda_cr", "Capacity": "_capacity",
                 "Generation": "generation_mu", "Capex": "capex_cr", "Debt": "gross_debt_cr"}
UNIT_NAMES = {"INR_cr": "₹ crore", "MW": "MW", "MU": "million units", "%": "%", "x": "times", "tCO2/MWh": "tCO2/MWh"}


# ------------------------------------------------------------------------------------------------
# state helpers
# ------------------------------------------------------------------------------------------------

@st.cache_resource
def get_store() -> Store:
    return Store(get_settings().db_path)


@st.cache_resource
def job_registry() -> JobRegistry:
    return JobRegistry()


@st.cache_data(ttl=900, show_spinner=False)
def market_quote(nse: str, period: str = "1Y") -> dict:
    return asdict(fetch_quote(nse, period=period))


@st.cache_data(ttl=900, show_spinner=False)
def index_quote(period: str = "1Y") -> dict:
    return asdict(fetch_chart(NIFTY50, period))


def run_id() -> str | None:
    return st.session_state.get("run_id")


def go_to(page: str, **state) -> None:
    """Button callback: switch page (and optional state) before the next rerun."""
    st.session_state["nav"] = page
    for k, v in state.items():
        st.session_state[k] = v


def link(page: str, text: str, **params) -> str:
    """HTML link to another page of this app; keeps the selected run."""
    q = {"page": SLUG[page], **({"run": run_id()} if run_id() else {}), **params}
    href = "?" + "&".join(f"{k}={v}" for k, v in q.items())
    return f"<a href='{esc(href)}' target='_self'>{esc(text)}</a>"


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def fmt_val(v, unit: str) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "n/a"
    u = {"INR_cr": " ₹ cr", "MW": " MW", "MU": " MU", "%": "%", "x": "x", "tCO2/MWh": " tCO2/MWh"}.get(unit, f" {unit}" if unit else "")
    if abs(v) >= 1000:
        return f"{v:,.0f}{u}"
    return f"{v:,.3f}{u}" if abs(v) < 1 else f"{v:,.2f}{u}"


def fmt_inr(v: float) -> str:
    """Indian digit grouping for ₹ crore figures (3,36,127)."""
    neg, n = v < 0, f"{abs(v):.0f}"
    if len(n) > 3:
        head, tail = n[:-3], n[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        n = ",".join(([head] if head else []) + groups + [tail])
    return ("-" if neg else "") + n


def chart(fig, title: str = "", height: int = 320, key: str = "") -> None:
    fig.update_layout(**PLOTLY_LAYOUT, height=height)
    if not isinstance(fig.data[0] if fig.data else None, (go.Pie, go.Indicator, go.Scattergeo)):
        # subplot axes (xaxis2, yaxis2, ...) do not pick up the layout defaults, so style them all here
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)", linecolor="#1E2D48", automargin=True,
                         tickfont=dict(color=MUTED, size=11))
        fig.update_yaxes(gridcolor="#18253D", linecolor="rgba(0,0,0,0)", automargin=True,
                         tickfont=dict(color=MUTED, size=11), title_font=dict(color=MUTED, size=11))
    if title:  # titled charts keep the legend underneath so the two never overlap
        fig.update_layout(title=dict(text=title, x=0.01, y=0.97), margin=dict(t=48),
                          legend=dict(orientation="h", yanchor="top", y=-0.14, x=0))
    st.plotly_chart(fig, config=PLOTLY_CONFIG, theme=None, key=key or None)


def panel(key: str, height: int | None = None):
    # newer Streamlit rejects height=None, so only pass a height when there is one
    if height:
        return st.container(border=True, key=f"panel_{key}", height=height)
    return st.container(border=True, key=f"panel_{key}")


def run_banner(store: Store, rid: str) -> None:
    run = store.get_run(rid)
    if run and run.mode == "demo":
        html("<div class='eia-banner demo'><b>Demo mode, synthetic data.</b> Aurora Grid Renewables is a fictitious "
             "company and every figure is invented to show how the agent works.</div>")


def need_run(store: Store) -> str | None:
    rid = run_id()
    if not rid or not store.get_run(rid):
        html("<div class='eia-empty'>No research run is selected yet. Search for a company in the bar above, or try "
             "the demo.</div>")
        st.button("Start research", type="primary", on_click=go_to, args=("Signal Radar",), key="need_run_go")
        return None
    run_banner(store, rid)
    return rid


def source_actions(row: dict, key: str) -> None:
    url = views.web_url(row["source_url"], row.get("page"))
    title = row.get("source_title") or row["source_url"]
    page = row.get("page")
    page_txt = f", page {page}" if page else ""
    if url:
        html(f"<div class='eia-src'><a href='{esc(url)}' target='_blank' rel='noopener'>{esc(title[:90])}</a>"
             f"{esc(page_txt)}, {esc(row.get('source_tier', ''))} source</div>")
    else:
        html(f"<div class='eia-src'>{esc(title[:90])}{esc(page_txt)}, "
             f"{esc(views.source_origin(row['source_url']).lower())}</div>")
    st.button("View page in document", key=f"view_{key}", on_click=go_to, args=("Evidence Explorer",),
              kwargs=dict(doc_source=row["source_id"], doc_page=page, doc_passage=row.get("passage", "")))


# ------------------------------------------------------------------------------------------------
# top bar
# ------------------------------------------------------------------------------------------------

def _search_go() -> None:
    """Search bar: resolve the company and start live research straight away (Signal Radar shows progress)."""
    q = (st.session_state.get("top_search") or "").strip()
    if q:
        st.session_state["company_query"] = q
        st.session_state["autostart"] = True
    st.session_state["mode"] = "Live research"
    go_to("Signal Radar")


def _set_mode(mode: str) -> None:
    """Live research opens the search form; Demo mode runs the synthetic demo at once and opens its results."""
    st.session_state["mode"] = mode
    if mode == "Demo mode":
        _run_demo_now()
    else:
        go_to("Signal Radar")


def _retry_run(rid: str) -> None:
    run = get_store().get_run(rid)
    if run:
        st.session_state["retry_company"] = run.company.model_dump()
        st.session_state["mode"] = "Live research"
    go_to("Signal Radar")


def top_bar() -> None:
    settings = get_settings()
    c0, c1, c2, c3, c4 = st.columns([0.9, 5.2, 0.55, 2.6, 0.9], vertical_alignment="center")
    with c0.popover("Pages"):  # navigation that never depends on the sidebar being open
        for p in PAGES:
            st.button(p, key=f"menu_{SLUG[p]}", on_click=go_to, args=(p,))
    c1.text_input("Search company", placeholder="Search company (e.g. NTPC, Tata Power, Adani Green...)",
                  key="top_search", label_visibility="collapsed", on_change=_search_go)
    c2.button("→", key="top_go", type="primary", on_click=_search_go, help="Research this company")
    if st.session_state.get("mode") not in ("Live research", "Demo mode"):
        st.session_state["mode"] = "Live research"
    active = "mode_live" if st.session_state["mode"] == "Live research" else "mode_demo"
    html(f"<style>.st-key-{active} button {{ background: #0B3550 !important; border-color: {CYAN} !important; "
         f"color: #FFFFFF !important; }}</style>")
    m1, m2 = c3.columns(2)
    m1.button("Live research", key="mode_live", on_click=_set_mode, args=("Live research",))
    m2.button("Demo mode", key="mode_demo", on_click=_set_mode, args=("Demo mode",))
    with c4.popover("Settings"):
        d = settings.describe()
        st.markdown("**Data providers**")
        st.markdown(f"Web search: `{settings.search_provider}`  \nLLM: `{settings.llm_provider}`  \n"
                    f"Research rounds: {settings.max_rounds}, sources per round: {settings.max_sources_per_round}")
        st.markdown("**API keys found in .env**")
        st.markdown("  \n".join(f"{k}: {'yes' if v else 'no'}" for k, v in d["keys_present"].items()))
        st.caption("Edit the .env file in the project folder and restart the app to change these.")


# ------------------------------------------------------------------------------------------------
# Evidence Passport + finding cards (used across pages)
# ------------------------------------------------------------------------------------------------

def finding_card(h, rank: int | None = None) -> None:
    lab = status_label(h.status)
    module = dict(MODULE_ORDER).get(h.module, h.module)
    html(f"<div class='eia-find' style='--c:{status_color(lab)}'>"
         f"<div>{f'<span class=rank>#{rank}</span>' if rank else ''}<span class='t'>{esc(h.title)}</span></div>"
         f"<div class='meta'>{status_chip(lab)}{gauge(h.strength.value, lab)}{direction_tag(h.direction)}"
         f"<span class='eia-faint'>{esc(module)}, rounds {h.round_created} to {h.round_updated}</span></div>"
         f"<div class='s'>{esc(h.statement)}</div></div>")


def render_passport(store: Store, rid: str, hyp_id: str, ctx: str) -> None:
    p = views.passport(store, rid, hyp_id)
    if not p:
        st.warning("This finding no longer exists in the selected run.")
        return
    h = p["hypothesis"]
    t1, t2, t3, t4 = st.tabs([f"Supporting evidence ({len(p['supporting'])})", f"Calculations ({len(p['calculations'])})",
                              "Challenge and limits", "Verification history"])
    with t1:
        if not p["supporting"]:
            st.caption("No supporting facts were found.")
        for i, r in enumerate(p["supporting"]):
            tag = status_chip("Supported").replace("Supported", "Verified in source") if r["status"] == "source_verified" \
                else status_chip("Unresolved").replace("Unresolved", "Not verified verbatim")
            per = r["period"] or "no period"
            if r["period_inferred"]:
                per += " (period taken from the document, not the sentence)"
            html(f"<div class='eia-ev'><div class='head'><span class='metric'>{esc(r['metric'])}</span>"
                 f"<span class='val'>{esc(fmt_val(r['value'], r['unit']))}</span><span class='eia-muted'>{esc(per)}, "
                 f"{esc(r['scope'])} scope</span>{tag}</div><div class='eia-quote'>{esc(r['passage'][:500])}</div></div>")
            source_actions(r, f"{ctx}_{hyp_id}_s{i}")
    with t2:
        if not p["calculations"]:
            st.caption("No calculation is attached to this finding.")
        for c in p["calculations"]:
            res = fmt_val(c["result"], c["unit"]) if c["result"] is not None else c["status"].replace("_", " ")
            ins = ", ".join(f"{esc(k)} = {v:,.2f}" if isinstance(v, (int, float)) else f"{esc(k)} = {esc(v)}"
                            for k, v in c["inputs"].items())
            html(f"<div class='eia-calc'><div style='display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap'>"
                 f"<b>{esc(c['name'])}</b><span class='r'>{esc(res)}</span></div>"
                 f"<div class='eia-muted' style='margin-top:4px'>Formula <code>{esc(c['formula'])}</code></div>"
                 f"<div class='eia-muted'>Inputs: {ins or 'none'}</div>"
                 f"<div class='eia-faint'>Input facts: {esc(', '.join(c['input_fact_ids']) or 'none')}"
                 f"{(' | input calculations: ' + esc(', '.join(c['input_calc_ids']))) if c['input_calc_ids'] else ''}"
                 f"{(' | ' + esc(c['notes'])) if c['notes'] else ''}</div></div>")
    with t3:
        html(f"<div class='eia-falsify'><b>This finding would be wrong if:</b> {esc(h.falsification or 'not stated')}</div>")
        a, b = st.columns(2)
        with a:
            html(section("Counterarguments"))
            for c in p["counterarguments"]:
                html(f"<div class='eia-check'>{esc(c)}</div>")
            html(section("Counter-checks run"))
            icons = {"opposes": ("Opposes", CORAL), "supports": ("Supports", CYAN), "neutral": ("Neutral", MUTED),
                     "no_evidence": ("No evidence found", MUTED)}
            for c in p["checks"]:
                t, col = icons.get(c["effect"], (c["effect"], MUTED))
                html(f"<div class='eia-check'><span style='color:{col};font-weight:600'>{esc(t)}</span> "
                     f"<span class='eia-faint'>{esc(c['check'].replace('_', ' '))}, weight {c['weight']}</span><br>"
                     f"{esc(c['note'])}</div>")
            if not p["checks"]:
                st.caption("No counter-checks apply to this finding.")
        with b:
            html(section("Limitations"))
            for c in p["limitations"] or ["None recorded."]:
                html(f"<div class='eia-check'>{esc(c)}</div>")
        if p["counter"]:
            html(section("Counter-evidence"))
            for i, r in enumerate(p["counter"]):
                html(f"<div class='eia-ev'><div class='head'><span class='metric'>{esc(r['metric'])}</span>"
                     f"<span class='val'>{esc(fmt_val(r['value'], r['unit']))}</span>"
                     f"<span class='eia-muted'>{esc(r['period'])}</span></div>"
                     f"<div class='eia-quote opp'>{esc(r['passage'][:500])}</div></div>")
                source_actions(r, f"{ctx}_{hyp_id}_c{i}")
        if h.interpretation:
            html(section("Interpretation"))
            st.caption("Written by the LLM and rejected automatically if it adds any number. Not evidence.")
            st.info(h.interpretation)
    with t4:
        for line in p["history"]:
            html(f"<div class='eia-check'>{esc(line)}</div>")
        if h.counter_queries:
            st.caption(("Counter-evidence searches run: " if h.counter_searched else "Counter-evidence searches planned: ")
                       + "; ".join(h.counter_queries))


# ------------------------------------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------------------------------------

def initials(name: str) -> str:
    words = [w for w in name.replace("(", " ").split() if w.lower() not in ("ltd", "limited", "the", "of", "and", "india")]
    return "".join(w[0] for w in words[:3]).upper() or "?"


def page_overview(store: Store) -> None:
    rid = run_id()
    if not rid or not store.get_run(rid):
        with panel("welcome"):
            html(f"<div class='eia-hero'>{SKYLINE}<span class='chip'>READY</span>"
                 f"<div class='t'>Research any listed Indian energy company</div>"
                 f"<div class='s'>Type a company name or NSE symbol in the search bar and press Enter. The agent reads "
                 f"its NSE filings and financial tables, runs six analyses and challenges its own findings.</div></div>")
            c1, c2, _ = st.columns([1.2, 1.2, 3])
            c1.button("Start live research", type="primary", key="welcome_live", on_click=go_to, args=("Signal Radar",),
                      kwargs={"mode": "Live research"})
            c2.button("Run the demo", key="welcome_demo", on_click=_run_demo_now)
        return
    run = store.get_run(rid)
    run_banner(store, rid)
    s = views.run_summary(store, rid)
    mods_with_data = sum(1 for m in store.module_results(rid).values() if m["status"] in ("ok", "partial"))
    if rid not in job_registry().running_run_ids() and (run.status == "running" or s["sources_ok"] == 0
                                                        or s["facts"] == 0 or mods_with_data == 0):
        empty_run_help(store, rid, run)
    header_strip(store, rid, run)
    t_dash, t_research, t_metrics, t_dev, t_ins = st.tabs(
        ["Dashboard", "Research summary", "Key metrics", "Latest developments", "Insights"])
    with t_dash:
        overview_dashboard(store, rid, run)
    with t_research:
        overview_executive(store, rid, run)
    with t_metrics:
        overview_metrics(store, rid)
    with t_dev:
        overview_developments(store, rid)
    with t_ins:
        overview_insights(store, rid)


def _run_demo_now() -> None:
    out = run_demo(get_store(), get_settings())  # about a second: no network, synthetic documents
    st.session_state.update(run_id=out.run_id, pending_run=out.run_id, mode="Demo mode")
    go_to("Overview")


def empty_run_help(store: Store, rid: str, run, key: str = "empty") -> None:
    errs = [e.message for e in store.events(rid) if e.level in ("warning", "error")][:6]
    if run.status == "running":
        title = "This research was interrupted before it finished"
        body = ("The app was closed or restarted while this run was still working, so only part of it was saved. "
                "Press Retry research to run it again; research now keeps going in the background even if you "
                "switch pages.")
    else:
        title = "This run found too little to analyse"
        body = ("Few or no documents could be read for this company, so the analyses had nothing to work with. "
                "Common causes: no internet access from this computer, the exchange site refusing the request, or the "
                "company having no NSE symbol. Retry, add a web-search key in .env, or upload the annual report as a "
                "PDF on Signal Radar.")
    with panel(key):
        html(ptitle(title) + f"<div class='eia-muted'>{esc(body)}</div>" +
             ("<div class='eia-src' style='margin-top:8px'>What went wrong: " +
              esc(" | ".join(e[:140] for e in errs)) + "</div>" if errs else ""))
        c1, c2, c3, _ = st.columns([1, 1.3, 1, 2])
        c1.button("Retry research", type="primary", key=f"{key}_retry", on_click=_retry_run, args=(rid,))
        c2.button("Upload documents instead", key=f"{key}_upload", on_click=go_to, args=("Signal Radar",),
                  kwargs={"mode": "Live research"})
        c3.button("Run the demo", key=f"{key}_demo", on_click=_run_demo_now)


def day_change(ch) -> str:
    """Day change badge; never prints '-0.0%' (rounds to an unsigned 0.00% in a neutral colour)."""
    if ch is None:
        return "<span class='ch' style='color:#62748F'>n/a</span>"
    if abs(ch) < 0.005:
        return "<span class='ch' style='color:#93A4BE'>0.00%</span>"
    arrow, col = ("▲", GREEN) if ch > 0 else ("▼", CORAL)
    return f"<span class='ch' style='color:{col}'>{arrow} {abs(ch):.2f}%</span>"


def header_strip(store: Store, rid: str, run) -> None:
    co = run.company
    cols = st.columns([2.2, 1.15, 1.15, 1.15], vertical_alignment="center")
    with cols[0], panel("hdr_co", 108):
        when = (run.finished_at or run.started_at or "")[:10]
        html(f"<div class='eia-co'><div class='logo' style='width:58px;height:58px;flex-basis:58px;font-size:1.1rem'>"
             f"{esc(initials(co.name))}</div><div><div class='n'>{esc(co.name)}"
             f"{f' <span class=eia-muted>(NSE: {esc(co.nse)})</span>' if co.nse else ''}</div>"
             f"<div class='ids'>{esc(co.segment or 'Energy')} | Energy analysis | as of {esc(when)}</div></div></div>")
    q = {"error": "demo"} if run.mode == "demo" else (market_quote(co.nse, "5D") if co.nse else {"error": "no NSE symbol"})
    with cols[1], panel("hdr_px", 108):
        if q.get("price") is not None and not q.get("error"):
            html(f"<div class='eia-kpi' style='min-height:0;padding:4px 6px'><div class='l' style='margin:0'>Market price</div>"
                 f"<div class='v'>₹{q['price']:,.2f}{day_change(q.get('change_pct'))}</div>"
                 f"<div class='src'>{esc(q['source'])}, {esc(q['as_of'])} · change vs previous close</div></div>")
        else:
            why = "synthetic company" if run.mode == "demo" else "not reachable right now"
            html(f"<div class='eia-kpi' style='min-height:0;padding:4px 6px'><div class='l' style='margin:0'>Market price</div>"
                 f"<div class='v'>n/a</div><div class='src'>Market data {why}.</div></div>")
    with cols[2], panel("hdr_52", 108):
        if q.get("high_52w") and q.get("low_52w"):
            pos = (q["price"] - q["low_52w"]) / (q["high_52w"] - q["low_52w"]) * 100 if q["high_52w"] > q["low_52w"] else 50
            html(f"<div class='eia-kpi' style='min-height:0;padding:4px 6px'><div class='l' style='margin:0'>52-week range</div>"
                 f"<div class='v' style='font-size:1rem'>₹{q['low_52w']:,.0f} – ₹{q['high_52w']:,.0f}</div>"
                 f"<div class='eia-meter'><div style='width:{pos:.0f}%;background:{CYAN}'></div></div></div>")
        else:
            html("<div class='eia-kpi' style='min-height:0;padding:4px 6px'><div class='l' style='margin:0'>52-week range</div>"
                 "<div class='v'>n/a</div></div>")
    n = index_quote("5D")
    with cols[3], panel("hdr_nifty", 108):
        if n.get("price") is not None and not n.get("error"):
            html(f"<div class='eia-kpi' style='min-height:0;padding:4px 6px'><div class='l' style='margin:0'>NIFTY 50</div>"
                 f"<div class='v'>{n['price']:,.0f}{day_change(n.get('change_pct'))}</div>"
                 f"<div class='src'>{esc(n['as_of'])} · change vs previous close</div></div>")
        else:
            html("<div class='eia-kpi' style='min-height:0;padding:4px 6px'><div class='l' style='margin:0'>NIFTY 50</div>"
                 "<div class='v'>n/a</div><div class='src'>Market data not reachable right now.</div></div>")


def financial_figure(fo: dict):
    """Revenue (bars) above EBITDA and PAT (lines): two panels on one period axis, each with its own scale,
    so the smaller series are readable without a misleading second y-axis on the same plot."""
    from plotly.subplots import make_subplots
    has_rev = bool(fo.get("Revenue"))
    has_low = bool(fo.get("EBITDA") or fo.get("PAT"))
    rows = 2 if has_rev and has_low else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.55, 0.45] if rows == 2 else [1.0])
    if has_rev:
        pts = fo["Revenue"]
        fig.add_bar(x=[p["period"] for p in pts], y=[p["value"] for p in pts], name="Revenue",
                    marker=dict(color=C_BLUE, cornerradius=4), row=1, col=1,
                    hovertemplate="Revenue: ₹%{y:,.0f} Cr<extra></extra>")
    low_row = 2 if rows == 2 else 1
    for lab, col in (("EBITDA", C_ORANGE), ("PAT", C_AQUA)):
        pts = fo.get(lab) or []
        if pts:
            fig.add_scatter(x=[p["period"] for p in pts], y=[p["value"] for p in pts], name=lab, mode="lines+markers",
                            line=dict(color=col, width=2), marker=dict(size=8, line=dict(color="#0D1628", width=2)),
                            row=low_row, col=1, hovertemplate=f"{lab}: ₹%{{y:,.0f}} Cr<extra></extra>")
    fig.update_yaxes(tickformat="~s", gridcolor="#18253D", automargin=True, tickfont=dict(color=MUTED, size=11))
    periods = sorted({p["period"] for pts in fo.values() for p in (pts or [])}, key=_period_key)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=periods, range=[-0.6, len(periods) - 0.4],
                     tickmode="array", tickvals=periods, ticktext=[short_period(p) for p in periods], tickangle=0,
                     automargin=True, tickfont=dict(color=MUTED, size=11), showgrid=False)
    fig.update_layout(showlegend=False)
    return fig


def short_period(p: str) -> str:
    """FY2026 -> FY26, Q1FY2027 -> Q1 FY27: short enough to sit level under a narrow bar."""
    m = re.fullmatch(r"(Q\d)?FY(\d{2})(\d{2})", p or "")
    return f"{m.group(1) + ' ' if m.group(1) else ''}FY{m.group(3)}" if m else p


def _period_key(p: str):
    m = re.search(r"(?:Q(\d))?FY(\d{4})", p or "")
    return (int(m.group(2)), int(m.group(1) or 5)) if m else (9999, 9, p)


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def _big(value: str, label: str, color: str = "#FFFFFF", sub: str = "") -> str:
    return (f"<div style='margin:6px 0 10px'><div class='eia-muted' style='font-size:.84rem'>{esc(label)}</div>"
            f"<div style='font-size:1.75rem;font-weight:700;color:{color};line-height:1.15'>{esc(value)}</div>"
            + (f"<div style='font-size:.85rem;margin-top:2px'>{sub}</div>" if sub else "") + "</div>")


def overview_dashboard(store: Store, rid: str, run) -> None:
    c1, c2, c3 = st.columns([1.12, 1, 1.05])
    # ---- column 1: financial performance + operational metrics --------------------------------
    with c1:
        with panel("fin", 420):
            fo = views.financial_overview(store, rid)
            rev, pat = fo["Revenue"], fo["PAT"]
            sub = []
            if rev:
                yoy = f", YoY <b style='color:{GREEN if (rev[-1]['yoy'] or 0) >= 0 else CORAL}'>{rev[-1]['yoy']:+.1f}%</b>" \
                    if rev[-1]["yoy"] is not None else ""
                sub.append(f"Revenue {esc(rev[-1]['period'])}: <b>₹{fmt_inr(rev[-1]['value'])} Cr</b>{yoy}")
            if pat:
                sub.append(f"Net profit {esc(pat[-1]['period'])}: <b>₹{fmt_inr(pat[-1]['value'])} Cr</b>")
            html(ptitle("Financial performance overview") + f"<div class='eia-muted' style='margin-top:-6px'>"
                 f"{' | '.join(sub) or 'Annual revenue, EBITDA and profit (₹ crore)'}</div>")
            if not any(fo.values()):
                html("<div class='eia-empty'>No annual revenue, EBITDA or profit figures were found in the sources.</div>")
            else:
                html(f"<div class='eia-legend' style='margin:6px 0 0'>"
                     f"<span><i style='background:{C_BLUE};height:8px'></i>Revenue</span>"
                     f"<span><i style='background:{C_ORANGE}'></i>EBITDA</span>"
                     f"<span><i style='background:{C_AQUA}'></i>Net profit (PAT)</span>"
                     f"<span class='eia-faint'>₹ crore</span></div>")
                chart(financial_figure(fo), "", 320, key="dash_fin")
        with panel("ops", 330):
            om = views.operational_metrics(store, rid)
            html(ptitle("Operational metrics"))
            if om["capacity"]:
                parts = " ".join(f"<span style='color:{SOURCE_COLORS.get(i['source'], MUTED)};margin-right:12px'>"
                                 f"{esc(i['source'])} {i['mw'] / 1000:,.1f} GW</span>" for i in om["mix"]["items"])
                html(_big(f"{om['capacity']['value'] / 1000:,.2f} GW", f"{om['capacity_label']}, {om['capacity']['period']}",
                          CYAN, parts))
            else:
                html(_big("n/a", "Installed capacity", MUTED, "<span class='eia-faint'>Not found in the sources.</span>"))
            a, b = st.columns(2)
            with a:
                u = om["under_construction"]
                html(_big(f"{u['value'] / 1000:,.2f} GW" if u else "n/a", "Capacity under construction",
                          GREEN if u else MUTED, f"<span class='eia-faint'>{esc(u['period'])}</span>" if u else ""))
            with b:
                g = om["generation"]
                sub = (f"<span style='color:{GREEN if (g['yoy'] or 0) >= 0 else CORAL}'>{g['yoy']:+.1f}% YoY</span>"
                       if g and g["yoy"] is not None else "")
                html(_big(f"{g['value']:,.0f} MU" if g else "n/a", f"Generation{', ' + g['period'] if g else ''}",
                          GREEN if g else MUTED, sub))
    # ---- column 2: Nifty benchmarking, ratios, verdict ----------------------------------------
    with c2:
        with panel("bench", 420):
            html(ptitle("NIFTY 50 benchmarking"))
            if st.session_state.get("bench_range") not in ("1M", "3M", "6M", "1Y", "5Y"):
                st.session_state["bench_range"] = "1Y"
            rng = st.segmented_control("Range", ["1M", "3M", "6M", "1Y", "5Y"], key="bench_range",
                                       label_visibility="collapsed") or "1Y"
            co = run.company
            if run.mode == "demo" or not co.nse:
                html("<div class='eia-empty'>No share-price history: "
                     f"{'the demo company is synthetic and not listed' if run.mode == 'demo' else 'no NSE symbol'}.</div>")
            else:
                from eia.providers.market import MarketQuote
                sq, iq = MarketQuote(**market_quote(co.nse, rng)), MarketQuote(**index_quote(rng))
                rp = relative_performance(sq, iq)
                if not rp["dates"]:
                    html(f"<div class='eia-empty'>Market data is not reachable right now "
                         f"({esc(sq.error or iq.error or 'no overlapping dates')}).</div>")
                else:
                    html(f"<div class='eia-muted'>{rng} return: <i style='display:inline-block;width:14px;height:3px;background:{C_BLUE};vertical-align:middle;margin-right:5px'></i>"
                         f"<b style='color:#E6EDF7'>{co.nse} {rp['stock'][-1]:+.1f}%</b> vs "
                         f"<i style='display:inline-block;width:14px;height:3px;background:{C_ORANGE};vertical-align:middle;margin:0 5px'></i>"
                         f"<b style='color:#E6EDF7'>NIFTY 50 {rp['index'][-1]:+.1f}%</b></div>")
                    fig = go.Figure()
                    fig.add_scatter(x=rp["dates"], y=rp["stock"], name=co.nse, line=dict(color=C_BLUE, width=2),
                                    hovertemplate=f"{co.nse}: %{{y:+.1f}}%<extra></extra>")
                    fig.add_scatter(x=rp["dates"], y=rp["index"], name="NIFTY 50", line=dict(color=C_ORANGE, width=2),
                                    hovertemplate="NIFTY 50: %{y:+.1f}%<extra></extra>")
                    fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor="#33476A")
                    chart(fig, "", 300, key="dash_bench")
                    st.caption(f"Rebased to 0% at the start of the period. Source: {sq.source}.")
        with panel("ratios", 160):
            html(ptitle("Balance-sheet ratios", "<span class='eia-faint'>from filings</span>"))
            cells = []
            for r in views.balance_ratios(store, rid):
                v = f"{r['value']:.2f}x" if r["value"] is not None else "n/a"
                col = MUTED if r["value"] is None else (CORAL if (r["label"].endswith("EBITDA") and r["value"] >= 5) or
                                                       (r["label"] == "Interest coverage" and r["value"] < 2) else CYAN)
                cells.append(f"<div style='flex:1;text-align:center' title='{esc(r['note'])}'><div class='eia-muted' "
                             f"style='font-size:.8rem'>{esc(r['label'])}</div><div style='font-size:1.45rem;font-weight:700;"
                             f"color:{col}'>{v}</div><div class='eia-faint'>{esc(r['period'] or 'not found')}</div></div>")
            html(f"<div style='display:flex;gap:8px'>{''.join(cells)}</div>")
        with panel("verdict", 170):
            vd = views.verdict(store, rid)
            rl = views.risk_level(store, rid)
            html(ptitle("Agent verdict", f"<span style='color:{ {'High': CORAL, 'Medium': AMBER, 'Low': GREEN}.get(rl['level'], MUTED)}'>"
                 f"risk signal {esc(rl['level'].lower())}</span>"))
            tot = vd["risk"] + vd["opportunity"] + vd["open"]
            pct = round(100 * (vd["risk"] + vd["opportunity"]) / tot) if tot else None
            html(f"<div class='eia-ring'>{ring(pct, CYAN, 92)}<div class='lg'>"
                 f"<div><i style='background:{CORAL}'></i>Supported risks: {vd['risk']}</div>"
                 f"<div><i style='background:{GREEN}'></i>Supported opportunities: {vd['opportunity']}</div>"
                 f"<div><i style='background:{AMBER}'></i>Open or weakened: {vd['open']}</div>"
                 f"<div class='eia-faint' style='display:block'>Ring: share of findings settled by evidence</div></div></div>")
    # ---- column 3: project pipeline, ESG, headlines -------------------------------------------
    with c3:
        with panel("pipe", 600):
            html(ptitle("Project pipeline and ESG"))
            locs = views.project_locations(store, rid)
            if locs:
                colors = {"Operating": GREEN, "Upcoming / mixed": CYAN, "Issue reported": CORAL}
                fig = go.Figure()
                for stt, col in colors.items():
                    pts = [d for d in locs if d["status"] == stt]
                    if pts:
                        fig.add_scattergeo(lat=[d["lat"] for d in pts], lon=[d["lon"] for d in pts], name=stt,
                                           text=[f"{d['state']}" for d in pts], mode="markers+text", textposition="top center",
                                           textfont=dict(color="#E6EDF7", size=10),
                                           marker=dict(size=[10 + min(22, (d["mw"] or 0) / 150) for d in pts], color=col,
                                                       line=dict(color="#070D1A", width=1)),
                                           hovertext=[f"<b>{d['state']}</b><br>{d['mentions']} disclosure(s)"
                                                      f"{', ' + format(d['mw'], ',.0f') + ' MW' if d['mw'] else ''}<br>"
                                                      f"{esc(d['examples'][0][:90])}" for d in pts], hoverinfo="text")
                fig.update_geos(lonaxis_range=[67, 98], lataxis_range=[6, 37], showcountries=True, countrycolor="#33476A",
                                showland=True, landcolor="#13213A", showocean=True, oceancolor="#070D1A",
                                showcoastlines=True, coastlinecolor="#33476A", bgcolor="rgba(0,0,0,0)",
                                projection_type="mercator", showframe=False)
                fig.update_layout(legend=dict(orientation="h", y=-0.02, x=0))
                chart(fig, "", 250, key="dash_map")
            else:
                html("<div class='eia-empty' style='padding:10px 4px'>No Indian state is named in the project "
                     "disclosures found, so nothing can be placed on the map.</div>")
            esg = views.esg_series(store, rid)
            a, b = st.columns(2)
            with a:
                share = esg["renewable_share"][-1]["value"] if esg["renewable_share"] else None
                if share is not None:
                    g = go.Figure(go.Indicator(mode="gauge+number", value=share, number=dict(suffix="%", font=dict(size=22)),
                                               gauge=dict(axis=dict(range=[0, 100], tickcolor="#33476A"),
                                                          bar=dict(color=GREEN), bgcolor="#13213A", borderwidth=0,
                                                          steps=[dict(range=[0, 100], color="#13213A")])))
                    g.update_layout(margin=dict(l=22, r=22, t=10, b=0))
                    html("<div class='eia-muted' style='font-size:.84rem'>Renewable share of capacity</div>")
                    chart(g, "", 170, key="dash_gauge")
                else:
                    html(_big("n/a", "Renewable share of capacity", MUTED))
            with b:
                it = esg["intensity"]
                ch = esg["intensity_change_pct"]
                sub = (f"<span style='color:{GREEN if ch < 0 else CORAL}'>{ch:+.0f}% since {esc(it[0]['period'])}</span>"
                       if ch is not None else "")
                html(_big(f"{it[-1]['value']:.3f}" if it else "n/a",
                          f"Emission intensity, tCO2/MWh{', ' + it[-1]['period'] if it else ''}", GREEN if it else MUTED, sub))
            up = views.upcoming_projects(store, rid, 5)
            if up:
                rows = "".join(f"<tr><td>{esc(_short(u['item'], 70))}</td><td style='white-space:nowrap'>"
                               f"{(format(u['mw'], ',.0f') + ' MW') if u['mw'] else '—'}</td><td style='white-space:nowrap;"
                               f"color:{CORAL if u['status'] == 'Delayed' else CYAN}'>{esc(u['status'])}</td></tr>"
                               for u in up)
                html("<div class='eia-muted' style='margin:4px 0'>Upcoming projects and pipeline</div>"
                     f"<table class='eia-table'><tr><th>Project / disclosure</th><th>Capacity</th><th>Status</th></tr>{rows}</table>")
            else:
                html("<div class='eia-faint'>No pipeline, award or delay disclosures found.</div>")
        with panel("news", 170):
            html(ptitle("Recent headlines", link("Timeline", "View all")))
            dev = views.recent_developments(store, rid, 4)
            if dev:
                html("<ul class='eia-news'>" + "".join(
                    f"<li><span class='eia-faint'>{esc(pd.to_datetime(d['date']).strftime('%d %b %Y'))}</span> "
                    f"{esc(_short(d['label'], 95))}</li>" for d in dev) + "</ul>")
            else:
                html("<div class='eia-empty' style='padding:6px 2px'>No dated announcements were found.</div>")


def overview_executive(store: Store, rid: str, run) -> None:
    s = views.run_summary(store, rid)
    hyps = store.hypotheses(rid)
    # ---- row 1: hero | progress | sources -------------------------------------------------------
    c1, c2, c3 = st.columns([2.1, 1.25, 1.05])
    with c1, panel("hero", 300):
        done = run.status == "completed"
        updated = (run.finished_at or run.started_at or "")[:16].replace("T", " ")
        try:
            updated = datetime.fromisoformat(run.finished_at or run.started_at).strftime("%d %b %Y, %H:%M UTC")
        except Exception:
            pass
        html(f"<div class='eia-hero'>{SKYLINE}<span class='chip'>{'RESEARCH COMPLETE' if done else 'PARTIAL RESULTS'}</span>"
             f"<div class='t'>{'Analysis complete' if done else 'Analysis finished with gaps'}</div>"
             f"<div class='s'>Analysed <b>{s['sources_ok']}</b> sources, <b>{s['facts']}</b> facts extracted, "
             f"<b class='g'>{s['hypotheses']}</b> findings tested</div><div class='u'>Last updated {esc(updated)}"
             f"{'' if done else '. Some sources or searches failed; see the research log.'}</div></div>")
        b1, b2, _ = st.columns([1.1, 1.1, 1.2])
        b1.button("View top findings", type="primary", key="hero_feed", on_click=go_to, args=("Discovery Feed",))
        b2.download_button("Download report", build_html(store, rid, 25),
                           f"energy_report_{run.company.name.lower().replace(' ', '_')[:30]}_{rid}"
                           f"{'_DEMO' if run.mode == 'demo' else ''}.html", "text/html", key="hero_dl")
    with c2, panel("progress", 300):
        steps = views.research_progress(store, rid)
        pct = round(100 * sum(1 for x in steps if x["done"]) / len(steps))
        html(ptitle("Research progress", f"<span class='big'>{pct}%</span>") +
             f"<div class='eia-bar'><div style='width:{pct}%'></div></div>" +
             "".join(f"<div class='eia-step'><span class='ok' style='background:{GREEN if x['done'] else '#33240A'};"
                     f"color:{'#04140A' if x['done'] else AMBER}'>{'✓' if x['done'] else '!'}</span>{esc(x['step'])}"
                     f"<span class='v'>{esc(x['value'])}</span></div>" for x in steps))
    with c3, panel("sources", 300):
        rows = views.sources_by_type(store, rid)
        html(ptitle("Sources analysed", f"<span class='big'>{s['sources_ok']}</span>") +
             ("".join(f"<div class='eia-srow'><span class='ic'></span>{esc(k)}<span class='v'>{v}</span></div>"
                      for k, v in rows) or "<div class='eia-empty'>No documents were read.</div>") +
             f"<div style='text-align:right;margin-top:10px;font-size:.85rem'>"
             f"{link('Evidence Explorer', 'View all sources', tab='sources')}</div>")

    # ---- row 2: highlights | confidence | outlook ------------------------------------------------
    c1, c2, c3 = st.columns([2.1, 1.25, 1.05])
    with c1, panel("highlights", 205):
        hl = views.highlights(store, rid)
        tiles = [
            (hl["opportunities"], "Supported opportunities", GREEN, "#0A2416", "↗", "Discovery Feed", {"filter": "opportunity"}),
            (hl["insights"], "Supported findings", BLUE, "#0B1C3D", "✓", "Discovery Feed", {"filter": "supported"}),
            (hl["risks"], "Potential risks", ORANGE, "#2A1607", "⚠", "Discovery Feed", {"filter": "risk"}),
            (hl["contradictions"], "Contradictions found", VIOLET, "#1D1240", "⇄", "Contradiction Lab", {}),
        ]
        cells = "".join(
            f"<a class='tile' target='_self' href='{esc(_href(pg, **prm))}' style='border-color:{c}88;background:{bg}'>"
            f"<span class='ic' style='color:{c}'>{ic}</span><div class='n' style='color:{c}'>{n}</div>"
            f"<div class='l' style='color:{c}'>{esc(lab)}</div></a>" for n, lab, c, bg, ic, pg, prm in tiles)
        html(ptitle("Key highlights") + f"<div class='eia-hl'>{cells}</div>")
    with c2, panel("confidence", 205):
        ec = views.evidence_confidence(store, rid)
        col = GREEN if (ec["pct"] or 0) >= 60 else AMBER if (ec["pct"] or 0) >= 35 else CORAL
        html(ptitle("Evidence confidence") +
             f"<div class='eia-ring'>{ring(ec['pct'], col)}<div class='lg'>"
             f"<div><i style='background:{GREEN}'></i>Strong ({ec['strong']})</div>"
             f"<div><i style='background:{AMBER}'></i>Moderate ({ec['moderate']})</div>"
             f"<div><i style='background:{CORAL}'></i>Weak or insufficient ({ec['weak']})</div>"
             f"<div class='eia-faint' style='display:block'>Share of {ec['total']} live findings with strong or "
             f"moderate evidence</div></div></div>")
    with c3, panel("outlook", 205):
        ol = views.outlook(store, rid)
        col = {"good": GREEN, "bad": CORAL, "warn": AMBER}.get(ol["tone"], MUTED)
        icon = {"good": "↗", "bad": "↘", "warn": "→"}.get(ol["tone"], "?")
        html(ptitle("Overall outlook") +
             f"<div class='eia-outlook'><div class='badge' style='border-color:{col};color:{col}'>{icon}</div><div>"
             f"<div class='h' style='color:{col}' title='Rule-based summary of supported findings, not a forecast.'>"
             f"{esc(ol['label'])}</div><div class='p'>{esc(ol['text'])}</div></div></div>")

    # ---- row 3: trends | energy mix | ESG -------------------------------------------------------
    c1, c2, c3 = st.columns([1.55, 1.1, 1.1])
    with c1, panel("trends", 470):
        html(ptitle("Financial and operational trends"))
        avail = [k for k, m in TREND_METRICS.items() if views.trend(store, rid, m)]
        if not avail:
            html("<div class='eia-empty'>No multi-year financial or operating series was found in the sources.</div>")
        else:
            if st.session_state.get("trend_metric") not in avail:
                st.session_state["trend_metric"] = avail[0]
            pick = st.selectbox("Trend metric", avail, key="trend_metric", label_visibility="collapsed")
            data = views.trend(store, rid, TREND_METRICS[pick or avail[0]])
            unit = data[0]["unit"]
            # a fall of more than 80% in one year is far more often a partial-year or misread figure than a real
            # collapse: still shown, but greyed and called out so it is checked against the source
            odd = [d for d in data if d["yoy"] is not None and d["yoy"] < -80]
            yo = [d for d in data if d["yoy"] is not None]
            per = [d["period"] for d in data]
            fig = make_subplots(rows=2 if yo else 1, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                                row_heights=[0.64, 0.36] if yo else [1.0])
            fig.add_bar(x=per, y=[d["value"] for d in data], name=pick or avail[0],
                        marker=dict(color=[C_GREY if d in odd else C_BLUE for d in data], cornerradius=4), row=1, col=1,
                        hovertemplate=f"%{{x}}: %{{y:,.0f}} {UNIT_NAMES.get(unit, unit)}<extra></extra>")
            if yo:
                fig.add_bar(x=[d["period"] for d in yo], y=[d["yoy"] for d in yo], name="YoY growth",
                            marker=dict(color=[C_GREY if d in odd else C_AQUA if d["yoy"] >= 0 else "#E66767" for d in yo],
                                        cornerradius=3),
                            row=2, col=1, hovertemplate="%{x} YoY: %{y:+.1f}%<extra></extra>")
                fig.update_yaxes(title_text="YoY", ticksuffix="%", zeroline=True, zerolinecolor="#33476A", row=2, col=1)
            fig.update_yaxes(title_text=UNIT_NAMES.get(unit, unit), tickformat="~s", row=1, col=1)
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=per, range=[-0.6, len(per) - 0.4],
                             tickmode="array", tickvals=per, ticktext=[short_period(p) for p in per], tickangle=0)
            fig.update_layout(showlegend=False)
            chart(fig, "", 300, key="ov_trend")
            if odd:
                st.caption("Grey: " + ", ".join(d["period"] for d in odd) + " fell more than 80% in one year, which usually "
                           "means a partial-year or misread figure. Check it in the Evidence Explorer.")
    with c2, panel("mix", 470):
        mix = views.energy_mix(store, rid)
        html(ptitle("Energy mix", f"<span class='eia-faint'>{esc(mix['period'] or '')}</span>"))
        if not mix["items"]:
            html("<div class='eia-empty'>Capacity by energy source (coal, gas, hydro, solar, wind, nuclear) was not "
                 "found in the sources.</div>")
        else:
            fig = go.Figure(go.Pie(labels=[i["source"] for i in mix["items"]], values=[i["mw"] for i in mix["items"]],
                                   hole=.68, sort=False, textinfo="none",
                                   marker=dict(colors=[SOURCE_COLORS.get(i["source"], MUTED) for i in mix["items"]],
                                               line=dict(color="#0D1628", width=2)),
                                   hovertemplate="%{label}: %{value:,.0f} MW (%{percent})<extra></extra>"))
            fig.update_layout(showlegend=False, annotations=[dict(text=f"<b>{mix['total']:,.0f} MW</b><br>"
                              f"<span style='font-size:11px;color:#93A4BE'>reported total</span>", x=.5, y=.5,
                              showarrow=False, font=dict(size=17, color="#FFFFFF"))])
            chart(fig, "", 220, key="ov_mix")
            html("<div class='eia-mix'>" + "".join(
                f"<div class='row'><i style='background:{SOURCE_COLORS.get(i['source'], MUTED)}'></i>{esc(i['source'])}"
                f"<span class='v'>{i['mw']:,.0f} MW, {i['share']:.1f}%</span></div>" for i in mix["items"]) + "</div>")
    with c3, panel("esg", 430):
        esg = views.esg_series(store, rid)
        ch = esg["intensity_change_pct"]
        right = (f"<span style='color:{GREEN if ch < 0 else CORAL};font-weight:700'>{'↓' if ch < 0 else '↑'} {abs(ch):.0f}%"
                 f"</span>") if ch is not None else ""
        html(ptitle("Emissions and sustainability", right))
        opts = [o for o, ok in (("Emission intensity", esg["intensity"]), ("Renewable share", esg["renewable_share"])) if ok]
        if not opts:
            html("<div class='eia-empty'>No emission-intensity or renewable-share data was found in the sources.</div>")
        else:
            if st.session_state.get("esg_metric") not in opts:
                st.session_state["esg_metric"] = opts[0]
            pick = st.segmented_control("ESG metric", opts, key="esg_metric", label_visibility="collapsed") or opts[0]
            data = esg["intensity"] if pick == "Emission intensity" else esg["renewable_share"]
            fig = go.Figure(go.Bar(x=[d["period"] for d in data], y=[d["value"] for d in data],
                                   marker=dict(color=C_AQUA, cornerradius=4), text=[f"{d['value']:.3g}" for d in data],
                                   textposition="outside", textfont=dict(color="#E6EDF7")))
            fig.update_yaxes(title_text="tCO2/MWh" if pick == "Emission intensity" else "% of capacity", gridcolor="#1E2D48")
            chart(fig, "", 270, key="ov_esg")
            if pick == "Emission intensity" and ch is not None:
                st.caption(f"Change from {data[0]['period']} to {data[-1]['period']}, from reported figures.")

    # ---- row 4: top findings | graph | timeline -------------------------------------------------
    c1, c2, c3 = st.columns([1.35, 1.3, 1.05])
    with c1, panel("topfind", 400):
        html(ptitle("Top findings", link("Discovery Feed", "View all")))
        if not hyps:
            html("<div class='eia-empty'>No findings yet: the sources did not contain enough evidence.</div>")
        colors = [GREEN, ORANGE, CYAN, AMBER, VIOLET]
        rows = []
        for i, h in enumerate(hyps[:3]):
            rows.append(f"<div class='eia-find-li'><span class='num' style='background:{colors[i]}'>{i + 1}</span><div>"
                        f"<div class='t'><a href='{esc(_href('Discovery Feed', focus=h.id))}' target='_self'>{esc(h.title)}</a></div>"
                        f"<div class='d'>{esc(_short(h.statement, 110))}</div></div>"
                        f"<span class='chip'>{status_chip(status_label(h.status))}<br>{strength_chip(h.strength.value)}</span></div>")
        html("".join(rows))
    with c2, panel("graph", 400):
        html(ptitle("Discovery graph", link("Discovery Graph", "Open full graph")))
        if hyps:
            g = build_graph(store, rid, [hyps[0].id], None, False)
            fig = graph_figure(g, 330, compact=True)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, config=PLOTLY_CONFIG, theme=None, key="ov_graph")
            st.caption(f"Evidence network for: {hyps[0].title}")
        else:
            html("<div class='eia-empty'>Nothing to map yet.</div>")
    with c3, panel("tl", 400):
        html(ptitle("Recent timeline", link("Timeline", "View full timeline")))
        dev = views.recent_developments(store, rid, 6)
        if not dev:
            html("<div class='eia-empty'>No dated announcements or targets were found.</div>")
        else:
            html("<div class='eia-tl'>" + "".join(
                f"<div class='row'><span class='dt'>{esc(pd.to_datetime(d['date']).strftime('%b %Y'))}</span>"
                f"<span class='dot'></span><span class='tx'>{esc(_short(d['label'], 72))}</span></div>" for d in dev) + "</div>")


def _short(label: str, n: int = 95) -> str:
    label = label.split(": ", 1)[1] if label.split(": ", 1)[0] in ("commissioning", "financing", "rating", "delay",
                                                                  "award", "ppa", "acquisition", "curtailment") else label
    return label if len(label) <= n else label[:n].rsplit(" ", 1)[0] + "…"


def _href(page: str, **params) -> str:
    q = {"page": SLUG[page], **({"run": run_id()} if run_id() else {}), **params}
    return "?" + "&".join(f"{k}={v}" for k, v in q.items())


def overview_metrics(store: Store, rid: str) -> None:
    df = views.key_metrics_table(store, rid)
    if df.empty:
        st.info("No reported metrics were extracted for this company. See the note at the top of the Overview for "
                "why, and use Retry research.")
        return
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Latest": st.column_config.NumberColumn(format="%.2f"),
                                "Previous": st.column_config.NumberColumn(format="%.2f"),
                                "YoY %": st.column_config.NumberColumn(format="%.1f%%")})
    st.caption("Latest value per metric as selected by the modules (preferred scope, verified, issuer sources first). "
               "Conflicts are values from other sources that differ by more than 2%.")
    keys = [k for k in METRICS if views.series_points(store, rid, k)]
    pick = st.selectbox("Chart a metric", keys, key="km_metric", format_func=metric_label)
    pts = views.series_points(store, rid, pick)
    fig = go.Figure(go.Bar(x=[p["period"] for p in pts], y=[p["value"] for p in pts], marker=dict(color=C_BLUE, cornerradius=4),
                           text=[f"{p['value']:,.4g}" for p in pts], textposition="outside", cliponaxis=False,
                           textfont=dict(color="#E6EDF7"), width=min(0.6, 0.18 * len(pts) + 0.12) if len(pts) < 4 else None))
    fig.update_xaxes(type="category")
    fig.update_yaxes(title_text=UNIT_NAMES.get(pts[0]["unit"], pts[0]["unit"]), rangemode="tozero")
    chart(fig, metric_label(pick), 320, key="km_chart")


def overview_developments(store: Store, rid: str) -> None:
    dev = views.recent_developments(store, rid, 60)
    if not dev:
        st.info("No dated announcements, financing events or targets were found.")
        return
    for i, d in enumerate(dev):
        with st.container(border=True, key=f"panel_dev_{i}"):
            html(f"<div class='eia-tl'><div class='row'><span class='dt'>{esc(pd.to_datetime(d['date']).strftime('%d %b %Y'))}"
                 f"</span><span class='dot'></span><span class='tx'><b>{esc(d['lane'])}</b><br>{esc(d['label'])}</span></div></div>")
            source_actions({"source_url": d["url"], "source_title": d["source"],
                            "page": int(d["page"]) if pd.notna(d["page"]) and d["page"] else None,
                            "source_id": _source_id(store, rid, d["fact_id"]), "passage": _passage(store, rid, d["fact_id"]),
                            "source_tier": ""}, f"dev_{i}")


def _source_id(store: Store, rid: str, fact_id: str) -> str:
    return next((f.source_id for f in store.facts(rid) if f.id == fact_id), "")


def _passage(store: Store, rid: str, fact_id: str) -> str:
    return next((f.passage for f in store.facts(rid) if f.id == fact_id), "")


def overview_insights(store: Store, rid: str) -> None:
    ol = views.outlook(store, rid)
    html(f"<div class='eia-banner live'><b>{esc(ol['label'])}.</b> {esc(ol['text'])}</div>")
    hyps = [h for h in store.hypotheses(rid) if status_label(h.status) in ("Supported", "Weakened", "Unresolved")][:6]
    if not hyps:
        st.info("No findings to interpret yet. Findings need at least two years of figures from the sources; see the "
                "note at the top of the Overview and use Retry research.")
        return
    llm_on = get_settings().llm_provider != "none"
    if not llm_on:
        st.caption("No LLM is configured, so these insights are the agent's own rule-based findings and counterarguments. "
                   "Set EIA_LLM_PROVIDER in .env to add short written interpretations.")
    for h in hyps:
        finding_card(h)
        if h.interpretation:
            html(f"<div class='eia-quote'>{esc(h.interpretation)}</div>")
        alt = next((c for c in h.counterarguments if not c.startswith("No opposing evidence")), None)
        if alt:
            html(f"<div class='eia-src'>Strongest counterpoint: {esc(alt)}</div>")


# ------------------------------------------------------------------------------------------------
# Signal Radar
# ------------------------------------------------------------------------------------------------

def page_signal_radar(store: Store) -> None:
    settings = get_settings()
    mode = st.session_state.get("mode", "Live research")
    if mode == "Demo mode":
        with panel("demo"):
            html(ptitle("Demo research") + "<div class='eia-sub'>Runs the full agent on Aurora Grid Renewables, a "
                 "fictitious company with synthetic documents. Nothing is fetched from the internet and no figure "
                 "describes a real company.</div>")
            d_rounds = st.slider("Research rounds", 1, 3, 3, key="demo_rounds")
            st.button("Run demo research", type="primary", key="run_demo", on_click=_run_demo_now)
        return
    with panel("live"):
        html(ptitle("Live research"))
        c1, c2 = st.columns([3, 1])
        q = c1.text_input("Company name or NSE symbol", placeholder="For example NHPC, Tata Power or KPIGREEN",
                          key="company_query")
        rounds = c2.slider("Research rounds", 1, 3, min(3, settings.max_rounds), key="live_rounds",
                           help="Each round searches, analyses and then challenges its findings. Capped at 3.")
        company = None
        if q:
            res = resolve(q)
            if res.status == "resolved":
                company = res.company
                html(f"<div class='eia-src'>Matched <b style='color:{CYAN}'>{esc(company.name)}</b>, NSE "
                     f"{esc(company.nse)}. {esc(company.resolution_note)}</div>")
            elif res.status == "ambiguous":
                st.warning(f"“{q}” matches more than one listed company. Pick the one you mean.")
                opts = [f"{c.name} (NSE {c.nse})" for c, _ in res.candidates]
                pick = st.selectbox("Company", ["Select a company"] + opts, key="ambiguous_pick")
                if pick != "Select a company":
                    company = res.candidates[opts.index(pick)][0].model_copy(
                        update={"resolution_note": "Chosen by the user among ambiguous matches."})
            else:
                st.warning(f"“{q}” is not in the list of listed energy companies.")
                if st.checkbox(f"Research “{q}” anyway, with its identity marked as unverified", key="allow_unreg"):
                    company = unregistered(q)
        with st.expander("Add documents or links (optional)"):
            uploads = st.file_uploader("Annual reports, results or presentations (PDF, HTML or TXT)",
                                       type=["pdf", "html", "htm", "txt"], accept_multiple_files=True, key="uploads")
            urls = st.text_area("Document links, one per line", key="seed_urls",
                                placeholder="https://www.example.com/annual-report-2025.pdf")
        free = "NSE annual reports, NSE filings and Screener financial tables (no key needed)" \
            if settings.direct_sources else "none"
        web = settings.search_provider if settings.search_provider != "none" else \
            "off (add a search key in .env to also search news, ratings and presentations)"
        st.caption(f"Sources: {free}. Web search: {web}. LLM: {settings.llm_provider}.")
        auto = st.session_state.pop("autostart", False)
        retry = st.session_state.pop("retry_company", None)
        if retry:
            from eia.schema import Company
            company, auto = Company(**retry), True
        if auto and company is None and q:
            st.info("Pick the company above, then press Run research.")
        busy = bool(job_registry().active())
        if st.button("Run research", type="primary", disabled=company is None or busy, key="run_live",
                     help="Another research run is still in progress" if busy else None) or (auto and company and not busy):
            seeds = [SeedDocument(f.name, f.getvalue(), "", f.type or "") for f in (uploads or [])]
            seed_urls = [u.strip() for u in (urls or "").splitlines() if u.strip()]
            start_research(store, settings, company, seeds, seed_urls, rounds)
    rid = run_id()
    if rid and store.get_run(rid):
        with st.expander("Research log of the selected run"):
            log = views.events_log_df(store, rid)
            if not log.empty:
                st.dataframe(log, hide_index=True, width="stretch")


def start_research(store: Store, settings, company, seeds, seed_urls, rounds: int) -> None:
    """Research runs in a background thread so clicking around the app can never interrupt it."""
    def work(job):
        agent = ResearchAgent(store, settings, progress=lambda st_, msg, fr: _track(job, agent, st_, msg, fr))
        return agent.research(company, mode="live", seed_documents=seeds, seed_urls=seed_urls, max_rounds=rounds)

    job = job_registry().start(company.name, work)
    st.session_state["job_id"] = job.id


def _track(job, agent, stage: str, msg: str, frac: float) -> None:
    if agent.run is not None:
        job.run_id = agent.run.id
    job.progress(stage, msg, frac)


@st.fragment(run_every=1.5)
def job_monitor() -> None:
    """Live progress for the current research job, shown on every page; opens the results when it finishes."""
    job = job_registry().get(st.session_state.get("job_id"))
    if job is None or job.seen:
        return
    if job.done:
        job.seen = True
        if job.run_id:
            st.session_state.update(run_id=job.run_id, pending_run=job.run_id, pending_nav="Overview")
        st.session_state["job_note"] = (f"Research on {job.label} finished: {job.summary}." if job.status != "failed"
                                        else f"Research on {job.label} failed: {job.error}")
        st.rerun()
    with panel("job"):
        elapsed = int(__import__("time").time() - job.started)
        html(ptitle(f"Researching {job.label}", f"<span class='eia-faint'>{elapsed}s, keeps running if you switch pages"
                                                f"</span>"))
        pct = min(1.0, max(0.02, job.frac)) * 100
        lines = "".join(f"<div class='ln' title='{esc(m)}'>{esc(m)}</div>" for m in job.messages[-4:])
        # one fixed-height block: the panel never changes size while messages stream in
        html(f"<div class='eia-job'><div class='eia-bar'><div style='width:{pct:.0f}%'></div></div>"
             f"<div class='msgs'>{lines}</div></div>")


# ------------------------------------------------------------------------------------------------
# Discovery Feed
# ------------------------------------------------------------------------------------------------

def page_discovery_feed(store: Store) -> None:
    rid = need_run(store)
    if not rid:
        return
    hyps = store.hypotheses(rid)
    if not hyps:
        run = store.get_run(rid)
        if rid in job_registry().running_run_ids():
            st.info("Research is still running. Findings appear here when it finishes.")
        else:
            empty_run_help(store, rid, run, key="feed_empty")
        return
    labels = sorted({status_label(h.status) for h in hyps})
    if st.session_state.get("feed_status") and not set(st.session_state["feed_status"]) <= set(labels):
        st.session_state["feed_status"] = [x for x in st.session_state["feed_status"] if x in labels]
    c1, c2, c3 = st.columns(3)
    stat = c1.multiselect("Status", labels, key="feed_status")
    dirs = c2.multiselect("Type", ["risk", "opportunity", "neutral"], key="feed_dir",
                          format_func=lambda d: {"risk": "Risk", "opportunity": "Opportunity", "neutral": "Observation"}[d])
    mods = c3.multiselect("Module", [k for k, _ in MODULE_ORDER], key="feed_mod",
                          format_func=lambda k: dict(MODULE_ORDER)[k])
    focus = st.session_state.get("feed_focus")
    shown = [(i, h) for i, h in enumerate(hyps, 1)
             if (not stat or status_label(h.status) in stat) and (not dirs or h.direction in dirs)
             and (not mods or h.module in mods)]
    st.caption(f"Showing {len(shown)} of {len(hyps)} findings.")
    for rank, h in shown:
        finding_card(h, rank)
        with st.expander("Open Evidence Passport", expanded=h.id == focus):
            render_passport(store, rid, h.id, "feed")


# ------------------------------------------------------------------------------------------------
# module pages
# ------------------------------------------------------------------------------------------------

def page_module(store: Store, key: str) -> None:
    rid = need_run(store)
    if not rid:
        return
    mr = store.module_results(rid).get(key)
    if not mr:
        st.info("This module has not run yet.")
        return
    html(f"<div style='margin:.2rem 0 .6rem'>{module_chip(mr['status'])}<span class='eia-muted'>{esc(mr['summary'])}</span></div>")
    if mr["missing"]:
        html(f"<div class='eia-src'>Not found in the sources, so not analysed: {esc(', '.join(mr['missing']))}.</div>")
    for n in mr["notes"]:
        html(f"<div class='eia-src' style='color:{AMBER}'>{esc(n)}</div>")
    metrics = [m for m in MODULE_CHARTS[key] if m in METRICS]
    sdf = views.metric_series_df(store, rid, metrics)
    if not sdf.empty:
        cols = st.columns(2)
        for i, (unit, g) in enumerate(sdf.groupby("unit")):
            fig = px.line(g, x="period", y="value", color="metric", markers=True, color_discrete_sequence=SERIES_COLORS,
                          labels={"value": UNIT_NAMES.get(unit, unit), "period": "", "metric": ""})
            fig.update_traces(line=dict(width=2.6), marker=dict(size=8))
            with cols[i % 2], panel(f"m_{key}_{i}"):
                chart(fig, f"Annual, {UNIT_NAMES.get(unit, unit)}", 320, key=f"mod_{key}_{unit}")
    qdf = views.metric_series_df(store, rid, metrics, "quarterly")
    for unit, g in (qdf.groupby("unit") if not qdf.empty else []):
        fig = px.bar(g, x="period", y="value", color="metric", barmode="group", color_discrete_sequence=SERIES_COLORS,
                     labels={"value": UNIT_NAMES.get(unit, unit), "period": "", "metric": ""})
        with panel(f"mq_{key}_{unit}"):
            chart(fig, f"Quarterly, {UNIT_NAMES.get(unit, unit)}", 300, key=f"modq_{key}_{unit}")
    if sdf.empty and qdf.empty:
        st.caption("No time series to chart for this module.")
    if mr["rows"]:
        html(section("Module table"))
        tbl = pd.DataFrame(mr["rows"]).astype(str)
        tbl.columns = [c.replace("_", " ").capitalize() for c in tbl.columns]
        st.dataframe(tbl, hide_index=True, width="stretch")
    mh = [h for h in store.hypotheses(rid) if h.module == key]
    html(section(f"Findings from this module ({len(mh)})"))
    if not mh:
        st.caption("No findings from this module.")
    for h in mh:
        finding_card(h)
        with st.expander("Open Evidence Passport"):
            render_passport(store, rid, h.id, f"mod_{key}")
    cdf = views.calculations_df(store, rid, key)
    with st.expander(f"All calculations in this module ({len(cdf)})"):
        if not cdf.empty:
            st.dataframe(cdf.drop(columns=["module"]), hide_index=True, width="stretch")


# ------------------------------------------------------------------------------------------------
# Graph, contradictions, timeline, evidence, report
# ------------------------------------------------------------------------------------------------

def page_graph(store: Store) -> None:
    rid = need_run(store)
    if not rid:
        return
    hyps = store.hypotheses(rid)
    if not hyps:
        st.info("There are no findings to map yet.")
        return
    labels = {f"{h.title} ({status_label(h.status)})": h.id for h in hyps}
    c1, c2 = st.columns([3, 2])
    pick = c1.multiselect("Findings to map", list(labels), default=list(labels)[:2], key="graph_pick")
    lab = c2.multiselect("Relationships", [l.value for l in RelLabel], default=[l.value for l in RelLabel],
                         key="graph_labels", format_func=str.capitalize)
    inc = st.toggle("Show source documents", value=True, key="graph_sources")
    if not pick:
        st.caption("Select at least one finding to draw its evidence network.")
        return
    g = build_graph(store, rid, [labels[p] for p in pick], lab or None, inc)
    html("<div class='eia-legend'>"
         f"<span><i style='background:{EDGE_COLORS['observed']}'></i>Observed in a source</span>"
         f"<span><i style='background:{EDGE_COLORS['inferred']}'></i>Inferred by calculation</span>"
         f"<span><i style='background:{EDGE_COLORS['contradictory']}'></i>Contradictory</span>"
         f"<span><i style='background:repeating-linear-gradient(90deg,{EDGE_COLORS['unverified']} 0 5px,transparent 5px 8px)'></i>Unverified (dashed)</span>"
         "<span class='eia-faint'>Read left to right: documents → facts → calculations → findings. Hover a node for its passage.</span>"
         f"<span>{len(g.nodes)} nodes, {len(g.edges)} links</span></div>")
    with panel("graphfull"):
        st.plotly_chart(graph_figure(g, 660), config=PLOTLY_CONFIG, theme=None, key="graph_fig")
    with st.expander("List of links"):
        if g.edges:
            st.dataframe(pd.DataFrame([{"From": g.nodes[e["src"]]["label"], "Relationship": e["relation"].replace("_", " "),
                                        "To": g.nodes[e["dst"]]["label"], "Label": e["label"], "Note": e["note"]}
                                       for e in g.edges]), hide_index=True, width="stretch")


def page_timeline(store: Store) -> None:
    rid = need_run(store)
    if not rid:
        return
    df = views.timeline_df(store, rid)
    if df.empty:
        st.info("No dated targets, announcements or results were found, so there is nothing to place on a timeline.")
        return
    lanes_all = ["Promise / target", "Milestone / announcement", "Financing", "Operating result", "Financial result"]
    lanes_present = [l for l in lanes_all if l in set(df["lane"])]
    lanes = st.multiselect("Show", lanes_present, default=lanes_present, key="tl_lanes")
    d = df[df["lane"].isin(lanes)]
    lane_color = dict(zip(lanes_all, SERIES_COLORS))
    fig = go.Figure()
    for lane in [l for l in lanes_all if l in lanes]:
        g = d[d["lane"] == lane]
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(g["date"]), y=[lane] * len(g), mode="markers", name=lane,
            marker=dict(size=13, color=lane_color[lane], symbol="diamond", line=dict(color="#070D1A", width=1)),
            hovertext=[f"<b>{r['label']}</b><br>{r['source']}" + (f", page {int(r['page'])}" if pd.notna(r["page"]) and r["page"] else "")
                       for r in g.to_dict("records")], hoverinfo="text+x"))
    fig.update_yaxes(categoryorder="array", categoryarray=[l for l in lanes_all if l in lanes][::-1])
    with panel("tlchart"):
        chart(fig, "From promise to cash", 440, key="timeline_fig")
    show = d.copy()
    show["link"] = [views.web_url(u, p) for u, p in zip(show["url"], show["page"])]
    show["page"] = show["page"].apply(lambda p: int(p) if pd.notna(p) and p else None)
    st.dataframe(show[["date", "lane", "label", "source", "page", "link"]], hide_index=True, width="stretch",
                 column_config={"date": "Date", "lane": "Lane", "label": "What happened", "source": "Source",
                                "page": "Page", "link": st.column_config.LinkColumn("Open source", display_text="Open")})
    st.caption("Open links go to the original web document. Synthetic and uploaded documents can be read in the "
               "Evidence Explorer.")


def page_contradictions(store: Store) -> None:
    rid = need_run(store)
    if not rid:
        return
    cons = views.contradictions(store, rid)
    contested = views.contested_hypotheses(store, rid)
    html(stat_strip([(len(cons), "Conflicting values", "same metric and period", "warn" if cons else ""),
                     (len(contested), "Contested findings", "evidence both ways or unresolved", "")]))
    html(section("Where sources disagree"))
    if not cons:
        st.caption("No source reports a different value for the same metric and period.")
    for ci, c in enumerate(cons):
        with st.expander(f"{c['metric']}, {c['period']}: values differ by {c['rel_diff_pct']}%"):
            cols = st.columns(max(1, len(c["facts"])))
            for j, (col, r) in enumerate(zip(cols, c["facts"])):
                with col:
                    sel = r["id"] == c["selected_fact_id"]
                    html(f"<div class='eia-ev'><div class='head'><span class='val'>{esc(fmt_val(r['value'], r['unit']))}</span>"
                         f"{status_chip('Supported').replace('Supported', 'Used in analysis') if sel else ''}</div>"
                         f"<div class='eia-muted'>{esc(r['scope'])} scope, {esc(r['source_tier'])} source</div>"
                         f"<div class='eia-quote'>{esc(r['passage'][:300])}</div></div>")
                    source_actions(r, f"con_{ci}_{j}")
            st.caption("The value used for analysis is chosen by reporting scope, verification, explicit period, source "
                       "type and confidence. Any finding that uses a conflicted value stays Unresolved.")
    html(section("Evidence for and against each finding"))
    if not contested:
        st.caption("No finding has opposing evidence.")
    for h in contested:
        with st.expander(f"{h['title']} ({h['status']}, {h['strength']} evidence)"):
            a, b = st.columns(2)
            with a:
                html(f"<b style='color:{CYAN}'>For</b> <span class='eia-faint'>{h['n_supporting_facts']} fact(s)</span>")
                html(f"<div class='eia-check'>{esc(h['statement'])}</div>")
                for c in h["supporting_checks"]:
                    html(f"<div class='eia-check'>{esc(c['note'])}</div>")
            with b:
                html(f"<b style='color:{CORAL}'>Against</b> <span class='eia-faint'>{h['n_counter_facts']} fact(s)</span>")
                if not h["opposing_checks"]:
                    html("<div class='eia-check eia-muted'>No opposing evidence. The status reflects evidence quality "
                         "or conflicting inputs.</div>")
                for c in h["opposing_checks"]:
                    html(f"<div class='eia-check'>{esc(c['note'])} <span class='eia-faint'>weight {c['weight']}</span></div>")
            html(f"<div class='eia-falsify' style='margin-top:8px'><b>Would be wrong if:</b> {esc(h['falsification'] or 'not stated')}</div>")
            st.caption("History: " + " | ".join(h["history"]))


def document_viewer(store: Store, rid: str) -> None:
    sources = [s for s in store.sources(rid) if s.fetch_status == "ok"]
    if not sources:
        st.caption("No documents were read in this run.")
        return
    ids = [s.id for s in sources]
    by_id = {s.id: s for s in sources}
    want = st.session_state.get("doc_source")
    if want in ids and st.session_state.get("_doc_applied") != (want, st.session_state.get("doc_page")):
        st.session_state["doc_select"] = want
        st.session_state["_doc_applied"] = (want, st.session_state.get("doc_page"))
        st.session_state.pop("doc_page_select", None)
    if st.session_state.get("doc_select") not in ids:
        st.session_state["doc_select"] = ids[0]
    sid = st.selectbox("Document", ids, key="doc_select", format_func=lambda i: by_id[i].title or by_id[i].url)
    src = by_id[sid]
    pages = views.document_pages(store, sid)
    url = views.web_url(src.url)
    meta = f"{src.doc_type.value.replace('_', ' ')}, {src.tier.value} source, {src.n_pages} page(s)"
    if url:
        html(f"<div class='eia-src'>{esc(meta)}. <a href='{esc(url)}' target='_blank' rel='noopener'>Open the "
             f"original document</a></div>")
    else:
        html(f"<div class='eia-src'>{esc(meta)}. {esc(views.source_origin(src.url))}.</div>")
    if not pages:
        st.caption("The text of this document was not stored (it was read by an older version of the app). "
                   "Run the research again to view it here.")
        return
    nums = [n for n, _ in pages]
    req = st.session_state.get("doc_page")
    default = nums.index(int(req)) if want == sid and req and int(req) in nums else 0
    if st.session_state.get("doc_page_select") not in nums:
        st.session_state["doc_page_select"] = nums[default]
    n = st.selectbox("Page", nums, key="doc_page_select") if len(nums) > 1 else nums[0]
    passage = st.session_state.get("doc_passage", "") if want == sid else ""
    if passage:
        html("<div class='eia-faint' style='margin-bottom:6px'>The cited passage is highlighted.</div>")
    html(f"<div class='eia-doc'>{highlight(dict(pages)[n], passage)}</div>")
    if url and src.url.lower().split('?')[0].endswith(".pdf"):
        html(f"<div class='eia-src' style='margin-top:6px'><a href='{esc(views.web_url(src.url, n))}' target='_blank' "
             f"rel='noopener'>Open page {n} of the original PDF</a></div>")


def page_evidence(store: Store) -> None:
    rid = need_run(store)
    if not rid:
        return
    names = ["Documents", "Facts", "Sources"]
    if st.session_state.get("evidence_tab") == "sources":
        names = ["Sources", "Documents", "Facts"]
    tabs = dict(zip(names, st.tabs(names)))
    with tabs["Documents"]:
        document_viewer(store, rid)
    with tabs["Facts"]:
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        q = c1.text_input("Search", placeholder="Word, number, metric or source", key="ev_q")
        mk = sorted({f.metric for f in store.facts(rid)})
        metrics = c2.multiselect("Metric", mk, key="ev_metric", format_func=lambda k: metric_label(k) if k != "event" else "Event")
        types = c3.multiselect("Type", ["reported", "target", "event"], key="ev_type", format_func=str.capitalize)
        stats = c4.multiselect("Verification", ["source_verified", "unverified"], key="ev_stat",
                               format_func=lambda s: "Verified" if s == "source_verified" else "Not verified")
        df = views.facts_df(store, rid, q, metrics or None, types or None, stats or None)
        st.caption(f"{len(df)} fact(s). Verified means the number was found word for word in the quoted passage.")
        if not df.empty:
            show = df.copy()
            show["link"] = [views.web_url(u, p) for u, p in zip(show["source_url"], show["page"])]
            st.dataframe(show[["metric", "type", "value", "unit", "period", "scope", "status", "page", "source_title",
                               "link", "passage"]], hide_index=True, width="stretch",
                         column_config={"metric": "Metric", "type": "Type",
                                        "value": st.column_config.NumberColumn("Value", format="%.2f"),
                                        "unit": "Unit", "period": "Period", "scope": "Scope", "status": "Verification",
                                        "page": "Page", "source_title": "Source",
                                        "link": st.column_config.LinkColumn("Original", display_text="Open"),
                                        "passage": st.column_config.TextColumn("Passage", width="large")})
            ids = df["id"].tolist()
            rows = df.set_index("id")
            if st.session_state.get("ev_fact") not in ids:
                st.session_state["ev_fact"] = ids[0]
            fid = st.selectbox("Inspect a fact", ids, key="ev_fact",
                               format_func=lambda i: f"{rows.loc[i, 'metric']}, {rows.loc[i, 'period'] or 'no period'}: "
                                                     f"{fmt_val(rows.loc[i, 'value'], rows.loc[i, 'unit'])}")
            r = df[df["id"] == fid].iloc[0].to_dict()
            html(f"<div class='eia-ev'><div class='head'><span class='metric'>{esc(r['metric'])}</span>"
                 f"<span class='val'>{esc(fmt_val(r['value'], r['unit']))}</span><span class='eia-muted'>raw “{esc(r['raw'])}”, "
                 f"{esc(r['period'] or 'no period')}, {esc(r['method'])} extraction</span></div>"
                 f"<div class='eia-quote'>{esc(r['passage'])}</div><div class='eia-faint'>{esc(r['epistemic'])}</div></div>")
            source_actions(r, f"ev_{fid}")
            used_h = [h for h in store.hypotheses(rid) if fid in h.supporting_fact_ids or fid in h.counter_fact_ids]
            used_c = [c for c in store.calculations(rid) if fid in c.input_fact_ids]
            st.caption(f"Used in {len(used_c)} calculation(s) and {len(used_h)} finding(s)"
                       + (": " + "; ".join(h.title for h in used_h) if used_h else "."))
    with tabs["Sources"]:
        sdf = views.sources_df(store, rid)
        if sdf.empty:
            st.caption("No sources were collected.")
        else:
            sdf["link"] = [views.web_url(u) for u in sdf["url"]]
            st.dataframe(sdf[["title", "doc_type", "tier", "status", "facts", "pages", "round", "purpose", "published",
                              "link", "error"]], hide_index=True, width="stretch",
                         column_config={"title": "Title", "doc_type": "Type", "tier": "Source type", "status": "Read",
                                        "facts": "Facts", "pages": "Pages", "round": "Round", "purpose": "Why fetched",
                                        "published": "Published",
                                        "link": st.column_config.LinkColumn("Original", display_text="Open"),
                                        "error": "Problem"})
            st.caption("Documents without an Open link are synthetic or uploaded; read them in the Documents tab.")


def page_report(store: Store) -> None:
    rid = need_run(store)
    if not rid:
        return
    run = store.get_run(rid)
    n = st.slider("Findings to include", 5, 40, 20, key="report_n")
    md = build_markdown(store, rid, n)
    rep_html = build_html(store, rid, n)
    stem = f"energy_report_{run.company.name.lower().replace(' ', '_')[:30]}_{rid}" + ("_DEMO" if run.mode == "demo" else "")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download HTML report", rep_html, f"{stem}.html", "text/html", type="primary", key="dl_html")
    c2.download_button("Download Markdown report", md, f"{stem}.md", "text/markdown", key="dl_md")
    facts = views.facts_df(store, rid)
    c3.download_button("Download facts as CSV", facts.to_csv(index=False) if not facts.empty else "",
                       f"{stem}_facts.csv", "text/csv", key="dl_csv")
    st.caption("The HTML report opens in any browser and keeps every source link.")
    with panel("reportprev"):
        st.markdown(md.replace("$", "\\$"))


# ------------------------------------------------------------------------------------------------
# main
# ------------------------------------------------------------------------------------------------

QP_KEYS = ("page", "run", "filter", "focus", "tab")


def _qp_sig(d) -> tuple:
    return tuple((k, d.get(k)) for k in QP_KEYS)


def apply_query_params() -> None:
    """Deep links (?page=…&run=…&filter=…&focus=…&tab=…) from the in-page HTML links. Applied once per URL
    change; the app's own URL updates are recorded so they never re-trigger this."""
    qp = st.query_params
    sig = _qp_sig(qp)
    if st.session_state.get("_qp_sig") == sig:
        return
    st.session_state["_qp_sig"] = sig
    page = FROM_SLUG.get(qp.get("page") or "")
    if page:
        st.session_state["nav"] = page
    if qp.get("run"):
        st.session_state["pending_run"] = qp.get("run")
    f = qp.get("filter")
    if f in ("risk", "opportunity"):
        st.session_state["feed_dir"], st.session_state["feed_status"] = [f], []
    elif f == "supported":
        st.session_state["feed_status"], st.session_state["feed_dir"] = ["Supported"], []
    elif page == "Discovery Feed":
        st.session_state["feed_status"], st.session_state["feed_dir"] = [], []
    st.session_state["feed_focus"] = qp.get("focus")
    st.session_state["evidence_tab"] = qp.get("tab")


def sidebar(store: Store) -> str:
    with st.sidebar:
        html("<div class='eia-brand'><div class='mark'><span>E</span></div><div><div class='name'>ENERGY INTELLIGENCE"
             "<span class='ai'>AI</span></div><div class='tag'>RESEARCH • REVEAL • REAL IMPACT</div></div></div>")
        pending_nav = st.session_state.pop("pending_nav", None)
        if pending_nav in PAGES:
            st.session_state["nav"] = pending_nav
        if st.session_state.get("nav") not in PAGES:
            st.session_state["nav"] = PAGES[0]
        page = st.session_state["nav"]
        html(nav_css([SLUG[p] for p in PAGES], SLUG[page]))
        for p in PAGES:  # plain buttons: identical look on every Streamlit version
            st.button(p, key=f"nav_{SLUG[p]}", on_click=go_to, args=(p,))
        st.divider()
        runs = store.list_runs()
        if runs:
            labels = {r.id: f"{'Demo: ' if r.mode == 'demo' else ''}{r.company.name}, {r.started_at[:16].replace('T', ' ')}"
                      for r in runs}
            pending = st.session_state.pop("pending_run", None)
            if pending in labels:
                st.session_state["run_select"] = pending
            if st.session_state.get("run_select") not in labels:
                st.session_state["run_select"] = run_id() if run_id() in labels else runs[0].id
            sel = st.selectbox("Research run", list(labels), key="run_select", format_func=lambda i: labels[i])
            if run_id() and sel != run_id():  # switching from one run to another, not first load
                for k in ("doc_source", "doc_page", "doc_passage", "doc_select", "doc_page_select", "_doc_applied",
                          "trend_metric", "esg_metric", "km_metric", "ev_fact", "graph_pick", "feed_focus"):
                    st.session_state.pop(k, None)
            st.session_state["run_id"] = sel
        else:
            st.caption("No research runs yet.")
    return page


def main() -> None:
    st.set_page_config(page_title="Energy Intelligence Agent", page_icon="⚡", layout="wide",
                       initial_sidebar_state="expanded")
    html(CSS)
    store = get_store()
    apply_query_params()
    page = sidebar(store)
    top_bar()
    note = st.session_state.pop("job_note", None)
    if note:
        (st.error if "failed" in note else st.success)(note)
    job_monitor()
    if page != "Overview":
        html(page_header(page, PAGE_HELP.get(page, "")))
    want = {"page": SLUG[page], **({"run": run_id()} if run_id() else {})}
    if _qp_sig(st.query_params) != _qp_sig(want):
        st.query_params.from_dict(want)  # shareable URL for the current page and run
    st.session_state["_qp_sig"] = _qp_sig(want)
    if page in MODULE_PAGES:
        page_module(store, MODULE_PAGES[page])
        return
    {
        "Overview": page_overview, "Signal Radar": page_signal_radar, "Discovery Feed": page_discovery_feed,
        "Discovery Graph": page_graph, "Contradiction Lab": page_contradictions, "Timeline": page_timeline,
        "Evidence Explorer": page_evidence, "Report Studio": page_report,
    }[page](store)


main()
