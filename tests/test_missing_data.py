"""Missing metrics must produce 'insufficient data', never invented values."""
from eia.agent import ResearchAgent
from eia.config import get_settings
from eia.db import Store
from eia.modules import run_all
from eia.providers.llm import NullLLM
from eia.providers.search import NullSearch

from .helpers import CO, annual, ctx, target


def test_all_modules_insufficient_with_no_facts():
    res = run_all(ctx([]))
    assert len(res) == 6
    for r in res.values():
        assert r.status == "insufficient_data", r.key
        assert not r.signals or all(s.insufficient for s in r.signals)
        assert not [c for c in r.calcs if c.result is not None]


def test_partial_data_only_affects_relevant_modules():
    facts = annual("revenue_cr", "INR_cr", {2022: 100, 2023: 110, 2024: 120, 2025: 130})
    res = run_all(ctx(facts))
    assert res["green_growth"].status == "partial"
    assert "Electricity generation" in res["green_growth"].missing
    assert res["promise_reality"].status == "insufficient_data"
    # capital module: debt/EBITDA etc. are reported as insufficient, never filled in
    cc = res["capital_cash"]
    assert all(c.result is None for c in cc.calcs if "Interest coverage" in c.name)


def test_target_without_actuals_is_unresolved():
    res = run_all(ctx([target("renewable_target_mw", 5000, "MW", 2030)]))
    pr = res["promise_reality"]
    assert pr.rows[0]["status"] == "Insufficient evidence"
    assert all(s.insufficient for s in pr.signals)


def test_agent_without_search_or_documents_completes_with_insufficient_data(tmp_path):
    st = Store(":memory:")
    s = get_settings(cache_dir=str(tmp_path))
    out = ResearchAgent(st, s, search=NullSearch(), llm=NullLLM()).research(CO, max_rounds=2)
    assert out.status in ("completed", "partial")
    assert out.n_facts == 0 and out.n_hypotheses == 0
    mods = st.module_results(out.run_id)
    assert all(m["status"] == "insufficient_data" for m in mods.values())
    msgs = " ".join(e.message for e in st.events(out.run_id))
    assert "No search provider configured" in msgs
