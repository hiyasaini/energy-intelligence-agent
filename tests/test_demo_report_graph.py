import re
from pathlib import Path

import pytest

from eia import views
from eia.db import Store
from eia.demo import DEMO_COMPANY, run_demo
from eia.graph import build_graph, graph_figure
from eia.report import build_html, build_markdown
from eia.schema import HypothesisStatus, SourceTier

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def demo():
    st = Store(":memory:")
    out = run_demo(st)
    return st, out


def test_demo_runs_full_pipeline(demo):
    st, out = demo
    run = st.get_run(out.run_id)
    assert run.mode == "demo" and out.status == "completed" and out.rounds == 3
    assert all(s.tier == SourceTier.synthetic for s in st.sources(out.run_id))
    assert all(f.extraction_method == "synthetic" for f in st.facts(out.run_id))
    mods = st.module_results(out.run_id)
    assert all(m["status"] in ("ok", "partial") for m in mods.values())


def test_demo_counterevidence_revises_a_hypothesis(demo):
    st, out = demo
    pipeline_src = [s for s in st.sources(out.run_id) if "pipeline" in s.url][0]
    assert pipeline_src.purpose == "counterevidence" and pipeline_src.round >= 2
    h = [h for h in st.hypotheses(out.run_id) if h.signal_key.startswith("promise_reality:pace")][0]
    assert h.status == HypothesisStatus.weakened
    assert any(c["check"] == "pipeline_covers_gap" and c["effect"] == "opposes" for c in h.checks)
    assert h.counter_fact_ids


def test_every_finding_has_a_passport(demo):
    st, out = demo
    for h in st.hypotheses(out.run_id):
        p = views.passport(st, out.run_id, h.id)
        assert p["supporting"] or h.status == HypothesisStatus.insufficient_evidence
        assert p["counterarguments"] and h.falsification is not None
        assert p["strength"] in ("strong", "moderate", "weak", "insufficient")
        for c in p["calculations"]:
            assert c["input_fact_ids"] or c["input_calc_ids"] or c["status"] != "ok"


def test_contradiction_is_surfaced(demo):
    st, out = demo
    cons = views.contradictions(st, out.run_id)
    assert any(c["metric"] == "Revenue from operations" and c["period"] == "FY2025" for c in cons)


def test_report_exports(demo):
    st, out = demo
    md = build_markdown(st, out.run_id)
    html = build_html(st, out.run_id)
    assert "DEMO MODE — SYNTHETIC DATA" in md and "DEMO MODE — SYNTHETIC DATA" in html
    assert "Falsification condition" in md
    # synthetic documents have no web address: labelled, never linked
    assert "](synthetic://" not in md and "href='synthetic://" not in html
    assert "synthetic demo document (not on the internet)" in md
    assert html.startswith("<!doctype html>") and "</html>" in html


def test_graph_labels(demo):
    st, out = demo
    g = build_graph(st, out.run_id)
    labels = {e["label"] for e in g.edges}
    assert {"observed", "inferred", "contradictory"} <= labels
    types = {n["type"] for n in g.nodes.values()}
    assert {"source", "fact", "calc", "hypothesis", "metric", "event"} <= types
    assert graph_figure(g).data


def test_timeline(demo):
    st, out = demo
    df = views.timeline_df(st, out.run_id)
    assert {"Promise / target", "Operating result", "Financial result"} <= set(df["lane"])


def test_no_company_specific_findings_in_live_code():
    """Generalisation guard: analysis code must not mention specific companies or the demo company."""
    names = [DEMO_COMPANY.name.split()[0]] + ["NTPC", "Adani", "Tata", "NHPC", "JSW", "Suzlon", "Waaree"]
    for p in (ROOT / "eia").rglob("*.py"):
        if p.name == "demo.py":
            continue
        text = p.read_text(encoding="utf-8")
        for n in names:
            assert not re.search(rf"\b{n}\b", text), f"{n} found in {p}"


def test_web_links_only_for_real_urls_and_pdf_pages():
    assert views.web_url("synthetic://x/y.txt") is None and views.web_url("upload://a.pdf") is None
    assert views.web_url("https://e.org/ar.pdf", 12) == "https://e.org/ar.pdf#page=12"
    assert views.web_url("https://e.org/ar.pdf", 12.0) == "https://e.org/ar.pdf#page=12"
    assert views.web_url("https://e.org/page.html", 3) == "https://e.org/page.html"


def test_document_text_is_stored_for_the_viewer(demo):
    st, out = demo
    for s in st.sources(out.run_id):
        assert st.pages(s.id), s.title


def test_discovery_brief_has_every_required_element(demo):
    from eia import discovery
    st, out = demo
    b = discovery.build(st, out.run_id)
    assert b["discovery"].endswith(".") and len(b["discovery"]) > 20          # 1. one sentence
    assert 3 <= len(b["why"]) <= 5                                           # 2. why it matters
    assert b["evidence"] and all(d["items"] for d in b["evidence"])         # 3. evidence with sources
    assert b["timeline"] and b["emerged"]                                    # 4. timeline
    assert all(c["result"] is not None for c in b["numbers"])               # 5. numbers
    assert b["counterargument"] and b["falsification"] != "n/a"             # 6, 7
    assert b["strength"] in ("strong", "moderate", "weak") and b["strength_reasons"]  # 8
    assert b["hypothesis"].status.value != "rejected"


def test_discovery_prefers_cross_document_findings(demo):
    from eia import discovery
    st, out = demo
    b = discovery.build(st, out.run_id)
    assert b["non_obvious"] and b["n_sources"] >= 2


def test_report_opens_with_the_discovery(demo):
    st, out = demo
    md = build_markdown(st, out.run_id)
    assert md.index("## The Discovery") < md.index("## Module overview")
    for piece in ("**Why it matters**", "**Counterargument.**", "**Falsification condition.**", "**Evidence strength"):
        assert piece in md
    assert "<h2>The Discovery</h2>" in build_html(st, out.run_id)
