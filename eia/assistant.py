"""Research assistant: answers questions about ONE research run from that run's own evidence.

It does not generate text with a language model and it never adds a number of its own. Every answer is
assembled from what the run already holds: findings (with their verification status and evidence grade),
reported series (with period and unit) and source documents. When nothing in the run matches the question, it
says so plainly instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .db import Store
from .discovery import build as build_discovery
from .metrics import metric_label
from .verification import status_label

# question words -> the reported series that answer them (checked in order; first match wins per series)
TOPICS: list[tuple[str, list[str]]] = [
    (r"revenue|sales|top ?line|turnover|income", ["revenue_cr"]),
    (r"ebitda|operating profit|margin", ["ebitda_cr", "revenue_cr"]),
    (r"profit|pat|earning|net income|bottom ?line", ["pat_cr"]),
    (r"debt|borrow|leverage|loan", ["gross_debt_cr", "ebitda_cr"]),
    (r"interest|finance cost|coverage", ["finance_cost_cr", "ebitda_cr"]),
    (r"cash|cfo|cash flow", ["cfo_cr"]),
    (r"capex|capital expenditure|spend|invest", ["capex_cr"]),
    (r"receivable|collection|dues", ["receivables_cr"]),
    (r"capacity|installed|mw|gw|renewable|solar|wind", ["installed_capacity_mw", "renewable_capacity_mw"]),
    (r"generation|electricity|output|plf|cuf", ["generation_mu"]),
    (r"coal|production|offtake|mine", ["coal_production_mt", "coal_offtake_mt"]),
    (r"oil|gas|crude|upstream", ["oil_gas_production_mtoe", "crude_production_mt", "gas_production_bcm"]),
    (r"refin|throughput", ["refinery_throughput_mt"]),
    (r"transmission|grid|line|ckm|substation|mva", ["transmission_ckm", "transformation_mva"]),
]
# question words -> finding types (signal_key prefixes or module keys)
FINDING_TOPICS: list[tuple[str, list[str]]] = [
    (r"risk|warning|concern|red flag|worr|problem", [":composite", "early_warning", "hidden_risk"]),
    (r"target|promise|plan|guidance|goal|deliver", ["promise_reality"]),
    (r"green|renewable|transition|capacity|growth", ["green_growth"]),
    (r"debt|leverage|cash|capital|interest|funding|capex", ["capital_cash"]),
    (r"delay|curtail|rating|downgrade|hidden", ["hidden_risk"]),
    (r"link|relationship|correlat|connect|lag", ["hidden_connections"]),
    (r"quarter|recent|latest|trend|slow|reversal", ["early_warning"]),
]
STOP = {"the", "a", "an", "is", "are", "was", "what", "whats", "how", "why", "does", "do", "of", "in", "on", "for",
        "to", "and", "or", "its", "it", "this", "that", "company", "about", "tell", "me", "show", "give", "any", "there"}
SUGGESTIONS = ["What is the key discovery?", "What are the main risks?", "How is debt moving?",
               "Are the targets on track?", "Which sources were used?"]


@dataclass
class Answer:
    text: str                                   # plain text with **bold** markers only
    cites: list[str] = field(default_factory=list)   # "Source title, p.N" strings
    finding_ids: list[str] = field(default_factory=list)


def _fmt(v: float, unit: str) -> str:
    if unit == "INR_cr":
        return f"₹{v:,.0f} cr"
    if unit == "%":
        return f"{v:.1f}%"
    return f"{v:,.1f} {unit}" if abs(v) < 100 else f"{v:,.0f} {unit}"


def _series_line(store: Store, rid: str, metric: str) -> str:
    from .views import trend
    pts = trend(store, rid, metric)
    if not pts:
        return ""
    last = pts[-1]
    s = f"**{metric_label(metric)}**: {_fmt(last['value'], last['unit'])} in {last['period']}"
    if last.get("yoy") is not None:
        s += f" ({last['yoy']:+.1f}% on {pts[-2]['period']})"
    if len(pts) >= 3:
        first = pts[0]
        s += f"; {_fmt(first['value'], first['unit'])} in {first['period']}"
    return s + "."


def _finding_line(h) -> str:
    return (f"**{h.title}** ({status_label(h.status)}, {h.strength.value} evidence). {h.statement}")


def briefing(store: Store, rid: str) -> Answer:
    """Opening message: the headline discovery, stated with its grade."""
    run = store.get_run(rid)
    if not run:
        return Answer("No research run is selected yet. Run the demo or research a company to start.")
    d = build_discovery(store, rid)
    hyps = store.hypotheses(rid)
    if not d or not d.get("title"):
        return Answer(f"I analysed **{run.company.name}** but found no finding with enough evidence to lead with. "
                      "Ask about a metric (revenue, debt, capacity) and I will show what the sources report.")
    n_sup = sum(1 for h in hyps if h.status.value == "supported")
    return Answer(f"I analysed **{run.company.name}** and tested {len(hyps)} finding(s); {n_sup} are supported by "
                  f"evidence. The lead discovery: **{d['title']}**. {d.get('discovery', '')} "
                  f"Status: {d.get('status', '')}, {d.get('strength', '')} evidence"
                  + (f", {d['n_sources']} source document(s)." if d.get("n_sources") else "."),
                  finding_ids=[d["hypothesis"].id] if d.get("hypothesis") else [])


def answer(store: Store, rid: str, question: str) -> Answer:
    q = (question or "").strip()
    if not q:
        return Answer("Ask me about this company's figures, findings, targets or sources.")
    run = store.get_run(rid)
    if not run:
        return Answer("No research run is selected yet.")
    ql = q.lower()
    if re.search(r"\b(discover|headline|key finding|main finding|summary|summar|overview)\w*", ql):
        return briefing(store, rid)
    if re.search(r"\bsource|document|where .* from|evidence base\b", ql):
        srcs = [s for s in store.sources(rid) if s.fetch_status == "ok"]
        if not srcs:
            return Answer("No source document was read successfully in this run.")
        lines = "; ".join(f"{s.title or s.url} ({s.n_pages or 1} page(s))" for s in srcs[:6])
        return Answer(f"This run read **{len(srcs)} source document(s)**: {lines}"
                      + (" and more." if len(srcs) > 6 else "."))

    hyps = [h for h in store.hypotheses(rid) if h.status.value != "rejected"]
    parts, ids = [], []
    # findings by topic
    keys = [k for rx, ks in FINDING_TOPICS if re.search(rx, ql) for k in ks]
    words = {w for w in re.findall(r"[a-z]{3,}", ql)} - STOP
    scored = []
    for h in hyps:
        text = f"{h.title} {h.statement} {h.module}".lower()
        topic = any(k in h.signal_key or h.module == k for k in keys)
        overlap = sum(1 for w in words if w in text)
        if topic or overlap >= 2 or (overlap and len(words) == 1):
            scored.append((topic * 2 + overlap + (h.status.value == "supported"), h))
    scored.sort(key=lambda x: -x[0])
    for _, h in scored[:3]:
        parts.append(_finding_line(h))
        ids.append(h.id)
    # reported figures by topic
    seen = set()
    for rx, metrics in TOPICS:
        if re.search(rx, ql):
            for m in metrics:
                if m in seen:
                    continue
                seen.add(m)
                line = _series_line(store, rid, m)
                if line:
                    parts.append(line)
            if len(seen) >= 3:
                break
    if not parts:
        return Answer(f"I could not find anything about \"{q}\" in this run's sources, so I will not guess. "
                      "Try asking about revenue, debt, capacity, targets, risks or sources.")
    return Answer("\n\n".join(parts), finding_ids=ids)
