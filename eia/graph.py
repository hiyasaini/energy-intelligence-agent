"""Discovery Graph: sources, facts, events/projects, metrics, calculations and hypotheses.

Edge labels:
  observed       stated directly in a source (fact extracted from source, fact supports a finding)
  inferred       produced by calculation or analysis (fact -> calc, calc -> hypothesis, metric co-movement)
  contradictory  evidence pointing the other way (conflicting values, counter-evidence)
  unverified     relies on a fact not located verbatim in its source
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .db import Store
from .metrics import metric_label
from .schema import FactStatus, Relationship, RelLabel

DERIVED = ("input_to", "supports", "contradicts_hypothesis", "concerns_metric")

# colour-blind-checked hues for a dark surface; 'unverified' is also dashed so it never relies on colour alone
EDGE_COLORS = {"observed": "#3987E5", "inferred": "#199E70", "contradictory": "#E66767", "unverified": "#C98500"}
NODE_COLORS = {"source": "#7D8BA0", "fact": "#3987E5", "event": "#D55181", "metric": "#C9D5E6",
               "calc": "#199E70", "hypothesis": "#C98500"}
NODE_NAMES = {"source": "Source document", "fact": "Fact", "event": "Event", "metric": "Metric",
              "calc": "Calculation", "hypothesis": "Finding"}


def persist_relationships(store: Store, run_id: str) -> int:
    """(Re)build analysis edges linking facts, calculations and hypotheses. Returns edge count written."""
    with store._lock:
        store.conn.execute(f"DELETE FROM relationships WHERE run_id=? AND relation IN ({','.join('?' * len(DERIVED))})",
                           (run_id, *DERIVED))
        store.conn.commit()
    facts = {f.id: f for f in store.facts(run_id)}
    calcs = {c.id: c for c in store.calculations(run_id)}
    rels: list[Relationship] = []
    used_calcs: set[str] = set()
    for h in store.hypotheses(run_id):
        for cid in h.calc_ids:
            if cid in calcs:
                used_calcs.add(cid)
                rels.append(Relationship(run_id=run_id, src_type="calc", src_id=cid, dst_type="hypothesis", dst_id=h.id,
                                         relation="supports", label=RelLabel.inferred))
        for fid in h.supporting_fact_ids:
            f = facts.get(fid)
            if not f:
                continue
            rels.append(Relationship(run_id=run_id, src_type="fact", src_id=fid, dst_type="hypothesis", dst_id=h.id,
                                     relation="supports",
                                     label=RelLabel.observed if f.status == FactStatus.source_verified
                                     else RelLabel.unverified))
        for fid in h.counter_fact_ids:
            if fid in facts:
                rels.append(Relationship(run_id=run_id, src_type="fact", src_id=fid, dst_type="hypothesis", dst_id=h.id,
                                         relation="contradicts_hypothesis", label=RelLabel.contradictory,
                                         note="counter-evidence"))
    # calculation inputs (including nested calcs used by hypothesis calcs)
    frontier = list(used_calcs)
    while frontier:
        cid = frontier.pop()
        c = calcs.get(cid)
        if not c:
            continue
        for fid in c.input_fact_ids:
            if fid in facts:
                rels.append(Relationship(run_id=run_id, src_type="fact", src_id=fid, dst_type="calc", dst_id=cid,
                                         relation="input_to", label=RelLabel.inferred))
        for sub in c.input_calc_ids:
            if sub in calcs:
                rels.append(Relationship(run_id=run_id, src_type="calc", src_id=sub, dst_type="calc", dst_id=cid,
                                         relation="input_to", label=RelLabel.inferred))
                if sub not in used_calcs:
                    used_calcs.add(sub)
                    frontier.append(sub)
    # facts -> metric nodes for facts involved in findings
    involved = {r.src_id for r in rels if r.src_type == "fact"}
    for fid in involved:
        f = facts[fid]
        if f.metric != "event":
            rels.append(Relationship(run_id=run_id, src_type="fact", src_id=fid, dst_type="metric", dst_id=f.metric,
                                     relation="concerns_metric", label=RelLabel.observed))
    store.upsert_many(rels)
    return len(rels)


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)   # node_key -> attrs
    edges: list[dict] = field(default_factory=list)


UNIT_SHORT = {"INR_cr": "₹ Cr", "pct": "%", "%": "%", "ratio": "x", "x": "x"}


def _val(v: float, unit: str) -> str:
    u = UNIT_SHORT.get(unit, unit)
    num = f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"
    return f"{num}{u}" if u in ("%", "x") else f"{num} {u}"


def _nk(t: str, i: str) -> str:
    return f"{t}:{i}"


def build_graph(store: Store, run_id: str, hypothesis_ids: Optional[list[str]] = None,
                labels: Optional[list[str]] = None, include_sources: bool = True) -> Graph:
    """Graph restricted to the evidence neighbourhood of the selected hypotheses (all if None)."""
    facts = {f.id: f for f in store.facts(run_id)}
    sources = {s.id: s for s in store.sources(run_id)}
    calcs = {c.id: c for c in store.calculations(run_id)}
    hyps = {h.id: h for h in store.hypotheses(run_id)}
    rels = store.relationships(run_id)
    want_h = set(hypothesis_ids) if hypothesis_ids else set(hyps)
    labels_ok = set(labels) if labels else {l.value for l in RelLabel}

    # neighbourhood: hypothesis <- facts/calcs <- facts(calc inputs) ; facts -> sources ; facts -> metrics
    keep: set[str] = {_nk("hypothesis", h) for h in want_h}
    adj: dict[str, list[Relationship]] = {}
    for r in rels:
        adj.setdefault(_nk(r.dst_type, r.dst_id), []).append(r)
    frontier = list(keep)
    seen_edges: list[Relationship] = []
    while frontier:
        n = frontier.pop()
        for r in adj.get(n, []):
            if r.relation == "extracted_from" or r.relation == "concerns_metric":
                continue
            s = _nk(r.src_type, r.src_id)
            seen_edges.append(r)
            if s not in keep:
                keep.add(s)
                frontier.append(s)
    # attach sources, metrics and fact-fact contradictions for kept facts
    kept_facts = {k.split(":", 1)[1] for k in keep if k.startswith("fact:")}
    for r in rels:
        if r.src_type == "fact" and r.src_id in kept_facts and r.relation in ("extracted_from", "concerns_metric"):
            if r.relation == "extracted_from" and not include_sources:
                continue
            seen_edges.append(r)
            keep.add(_nk(r.dst_type, r.dst_id))
        if r.relation == "contradicts" and r.src_type == "fact" and (r.src_id in kept_facts or r.dst_id in kept_facts):
            seen_edges.append(r)
            keep.add(_nk("fact", r.src_id))
            keep.add(_nk("fact", r.dst_id))
        if r.relation == "linked_to" and r.src_type == "metric" and _nk("metric", r.src_id) in keep:
            seen_edges.append(r)
            keep.add(_nk("metric", r.dst_id))

    g = Graph()
    for k in keep:
        t, i = k.split(":", 1)
        if t == "hypothesis" and i in hyps:
            h = hyps[i]
            g.nodes[k] = {"type": "hypothesis", "label": h.title[:60], "detail": f"{h.status.value} · {h.strength.value}"
                          f"<br>{h.statement[:200]}", "status": h.status.value}
        elif t == "fact" and i in facts:
            f = facts[i]
            typ = "event" if f.metric == "event" else "fact"
            val = _val(f.value, f.unit) if f.value is not None else ""
            name = f.event_category if typ == "event" else metric_label(f.metric)
            g.nodes[k] = {"type": typ, "label": f"{name} {f.period} {val}".strip()[:60],
                          "detail": f"{f.fact_type.value} · {f.status.value} · p.{f.page or '?'}<br>{f.passage[:200]}"}
        elif t == "calc" and i in calcs:
            c = calcs[i]
            res = _val(c.result, c.unit) if c.result is not None else c.status
            g.nodes[k] = {"type": "calc", "label": f"{c.name[:45]} = {res}"[:70], "detail": c.formula}
        elif t == "source" and i in sources:
            s = sources[i]
            g.nodes[k] = {"type": "source", "label": (s.title or s.domain)[:50],
                          "detail": f"{s.tier.value} · {s.doc_type.value}<br>{s.url[:120]}"}
        elif t == "metric":
            g.nodes[k] = {"type": "metric", "label": metric_label(i), "detail": "metric"}
    dedup = set()
    for r in seen_edges:
        a, b = _nk(r.src_type, r.src_id), _nk(r.dst_type, r.dst_id)
        key = (a, b, r.relation)
        if a in g.nodes and b in g.nodes and key not in dedup and r.label.value in labels_ok:
            dedup.add(key)
            g.edges.append({"src": a, "dst": b, "relation": r.relation, "label": r.label.value, "note": r.note})
    # drop isolated nodes created by label filtering (but keep selected hypotheses)
    linked = {e["src"] for e in g.edges} | {e["dst"] for e in g.edges}
    g.nodes = {k: v for k, v in g.nodes.items() if k in linked or v["type"] == "hypothesis"}
    return g


COLUMNS = {"source": 0, "fact": 1, "event": 1, "calc": 2, "hypothesis": 3}
COLUMN_TITLES = ["Source documents", "Facts and events", "Calculations", "Findings"]
MAX_PER_COLUMN = 16


def _short(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _layered(g: Graph) -> tuple[dict[str, tuple[float, float]], dict[int, int], int]:
    """Left-to-right layers (sources -> facts -> calculations -> findings). Within a layer, nodes are ordered by
    the average position of their neighbours (fewer crossings); crowded layers keep their best-connected nodes."""
    nbrs: dict[str, set[str]] = {k: set() for k in g.nodes}
    for e in g.edges:
        if e["src"] in nbrs and e["dst"] in nbrs:
            nbrs[e["src"]].add(e["dst"])
            nbrs[e["dst"]].add(e["src"])
    cols: dict[int, list[str]] = {c: [] for c in range(4)}
    for k, v in g.nodes.items():
        if v["type"] in COLUMNS:
            cols[COLUMNS[v["type"]]].append(k)
    hidden: dict[int, int] = {}
    for c, ks in cols.items():
        if len(ks) > MAX_PER_COLUMN:
            ks.sort(key=lambda k: -len(nbrs[k]))
            hidden[c] = len(ks) - MAX_PER_COLUMN
            cols[c] = ks[:MAX_PER_COLUMN]
    order: dict[str, float] = {}
    cols[3].sort(key=lambda k: g.nodes[k]["label"])
    for i, k in enumerate(cols[3]):
        order[k] = i
    for c in (2, 1, 0):  # sweep right-to-left, then once left-to-right
        cols[c].sort(key=lambda k: (sum(order.get(n, 0) for n in nbrs[k]) / max(1, sum(n in order for n in nbrs[k]))))
        for i, k in enumerate(cols[c]):
            order[k] = i * (len(cols[3]) or 1) / max(1, len(cols[c]))
    for c in (1, 2):
        cols[c].sort(key=lambda k: (sum(order.get(n, 0) for n in nbrs[k]) / max(1, len(nbrs[k]))))
    tallest = max((len(v) for v in cols.values()), default=1) or 1
    pos: dict[str, tuple[float, float]] = {}
    for c, ks in cols.items():
        n = len(ks)
        for i, k in enumerate(ks):  # centred vertically, same spacing in every column
            pos[k] = (float(c), -(i - (n - 1) / 2))
    return pos, hidden, tallest


def _curve(x0: float, y0: float, x1: float, y1: float, steps: int = 14) -> tuple[list, list]:
    xs, ys = [], []
    for j in range(steps + 1):
        t = j / steps
        a, b, c_, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        mx = (x0 + x1) / 2
        xs.append(a * x0 + b * mx + c_ * mx + d * x1)
        ys.append(a * y0 + b * y0 + c_ * y1 + d * y1)
    return xs + [None], ys + [None]


def graph_figure(g: Graph, height: int = 640, compact: bool = False):
    """Layered evidence map: sources on the left, findings on the right, every node labelled.
    Hover any node for the full passage, formula or statement; zoom and pan are enabled."""
    import plotly.graph_objects as go

    pos, hidden, tallest = _layered(g)
    traces = []
    for lab, color in EDGE_COLORS.items():
        xs, ys = [], []
        for e in g.edges:
            if e["label"] != lab or e["src"] not in pos or e["dst"] not in pos:
                continue
            (x0, y0), (x1, y1) = pos[e["src"]], pos[e["dst"]]
            if x0 > x1:
                (x0, y0), (x1, y1) = (x1, y1), (x0, y0)
            cx, cy = _curve(x0, y0, x1, y1) if x0 != x1 else ([x0, x1, None], [y0, y1, None])
            xs += cx
            ys += cy
        if xs:
            traces.append(go.Scatter(x=xs, y=ys, mode="lines", name=f"{lab.capitalize()} link",
                                     line=dict(color=color, width=1.4, dash="dash" if lab == "unverified" else "solid"),
                                     opacity=0.55, hoverinfo="skip"))
    sizes = {"hypothesis": 18, "calc": 12, "fact": 11, "event": 12, "source": 14}
    symbols = {"hypothesis": "diamond", "calc": "square", "fact": "circle", "event": "star", "source": "triangle-right"}
    text_at = {"source": "middle left", "hypothesis": "middle right"}
    for typ in ("source", "fact", "event", "calc", "hypothesis"):
        ks = [k for k, v in g.nodes.items() if v["type"] == typ and k in pos]
        if not ks:
            continue
        width = 44 if typ == "hypothesis" else 34 if typ == "source" else 36
        show_text = not compact or typ == "hypothesis"
        traces.append(go.Scatter(
            x=[pos[k][0] for k in ks], y=[pos[k][1] for k in ks], mode="markers+text" if show_text else "markers",
            name=NODE_NAMES[typ], text=[_short(g.nodes[k]["label"], width) for k in ks] if show_text else None,
            textposition=text_at.get(typ, "top center"),
            textfont=dict(color="#E6EDF7" if typ in ("source", "hypothesis") else "#AEBBD0", size=11 if not compact else 10),
            hovertext=[f"<b>{g.nodes[k]['label']}</b><br>{g.nodes[k]['detail']}" for k in ks], hoverinfo="text",
            marker=dict(size=sizes[typ], color=NODE_COLORS[typ], symbol=symbols[typ], line=dict(color="#0D1628", width=2))))
    top = (tallest - 1) / 2 + 0.9
    ann = [dict(x=c, y=top, text=f"<b>{t}</b>", showarrow=False, font=dict(color="#93A4BE", size=12), yanchor="bottom")
           for c, t in enumerate(COLUMN_TITLES) if any(p[0] == c for p in pos.values())]
    ann += [dict(x=c, y=-(tallest - 1) / 2 - 0.9, text=f"+{n} more (see the list of links)", showarrow=False,
                 font=dict(color="#62748F", size=11)) for c, n in hidden.items()]
    if compact:
        ann = []
    fig = go.Figure(traces)
    fig.update_layout(height=height if compact else max(height, int(40 * tallest + 140)), showlegend=not compact,
                      paper_bgcolor="#0F1A2E", plot_bgcolor="#0F1A2E", annotations=ann,
                      font=dict(color="#C9D5E6", family="Inter, sans-serif"), margin=dict(l=10, r=10, t=10, b=10),
                      hoverlabel=dict(bgcolor="#16233B", bordercolor="#1E2D48", font=dict(color="#E6EDF7")),
                      legend=dict(orientation="h", y=-0.02, yanchor="top", x=0, font=dict(size=11)),
                      xaxis=dict(visible=False, range=[-1.3, 4.6] if not compact else [-0.3, 3.9], fixedrange=False),
                      yaxis=dict(visible=False, range=[-(tallest - 1) / 2 - 1.3, top + 0.6]), dragmode="pan")
    return fig
