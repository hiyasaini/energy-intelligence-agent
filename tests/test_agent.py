"""Agent loop with offline doubles: relevance filtering, failures preserved as partial results, counter-search."""
from datetime import date

from eia.agent import ResearchAgent, SeedDocument
from eia.config import get_settings
from eia.db import Store
from eia.identity import resolve
from eia.providers.fetch import FetchResult
from eia.providers.llm import NullLLM
from eia.providers.search import SearchResult, StaticSearch
from eia.schema import Company

CO = Company(name="Kestrel Hydro Power Ltd", nse="KESTREL", website="kestrelhydro.example")

AR = """<html><head><title>Kestrel Hydro Power annual report 2024-25</title></head><body>
<p>(₹ in crore)</p><table>
<tr><th>Particulars</th><th>FY2022</th><th>FY2023</th><th>FY2024</th><th>FY2025</th></tr>
<tr><td>Revenue from operations</td><td>900</td><td>950</td><td>1,010</td><td>1,060</td></tr>
<tr><td>EBITDA</td><td>600</td><td>630</td><td>650</td><td>655</td></tr>
<tr><td>Finance costs</td><td>200</td><td>240</td><td>300</td><td>380</td></tr>
<tr><td>Total borrowings</td><td>3,000</td><td>3,600</td><td>4,400</td><td>5,300</td></tr>
</table>
<p>Installed capacity stood at 1,200 MW as on 31 March 2025.</p>
<p>The company targets installed capacity of 3,000 MW by FY2030.</p>
</body></html>"""

PRES = """<html><head><title>Kestrel Hydro investor presentation</title></head><body>
<table><tr><th>Particulars</th><th>FY2023</th><th>FY2024</th><th>FY2025</th></tr>
<tr><td>Installed capacity (MW)</td><td>1,000</td><td>1,100</td><td>1,200</td></tr></table>
</body></html>"""


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if url.endswith("ar.html"):
            return FetchResult(url, True, AR.encode(), "text/html", url)
        if url.endswith("pres.html"):
            return FetchResult(url, True, PRES.encode(), "text/html", url)
        return FetchResult(url, False, error="HTTP 503")


class FlakySearch(StaticSearch):
    def search(self, query, n=8):
        if "credit rating" in query:
            raise RuntimeError("provider timeout")
        return super().search(query, n)


def make_agent(store):
    search = FlakySearch({
        "annual report": [SearchResult("Kestrel Hydro Power annual report 2024-25", "https://kestrelhydro.example/ar.html"),
                          SearchResult("Other Power Co annual report", "https://otherpower.example/ar.html")],
        "investor presentation": [SearchResult("Kestrel Hydro investor presentation",
                                               "https://kestrelhydro.example/pres.html")],
        "quarterly results": [SearchResult("Kestrel Hydro Q1 results", "https://kestrelhydro.example/q1.pdf")],
    })
    fetcher = FakeFetcher()
    agent = ResearchAgent(store, get_settings(max_sources_per_round=5), search=search, llm=NullLLM(), fetcher=fetcher,
                          today=date(2025, 8, 1))
    return agent, search, fetcher


def test_live_pipeline_on_unfamiliar_company_with_failures():
    st = Store(":memory:")
    agent, search, fetcher = make_agent(st)
    out = agent.research(CO, max_rounds=3)
    assert out.status == "partial"  # search failure was logged but research continued
    assert "https://otherpower.example/ar.html" not in fetcher.calls  # wrong company filtered out
    srcs = {s.url: s for s in st.sources(out.run_id)}
    assert srcs["https://kestrelhydro.example/q1.pdf"].fetch_status == "failed"
    assert srcs["https://kestrelhydro.example/ar.html"].fetch_status == "ok"
    facts = st.facts(out.run_id)
    assert any(f.metric == "capacity_target_mw" and f.target_year == 2030 for f in facts)
    hyps = st.hypotheses(out.run_id)
    titles = " ".join(h.title for h in hyps)
    assert "faster than EBITDA" in titles  # debt CAGR 20.9% vs EBITDA 2.9%
    assert any(h.module == "promise_reality" for h in hyps)
    # counter-evidence queries were planned and issued in later rounds
    assert any(q for q in search.queries if "capacity under construction" in q or "equity" in q.lower())
    assert any(s.purpose == "counterevidence" for s in st.sources(out.run_id)) or \
        any("counter" in e.message.lower() or e.stage == "search" for e in st.events(out.run_id))
    errors = [e for e in st.events(out.run_id) if e.level == "error"]
    assert errors and "provider timeout" in errors[0].message
    # every calculation links to stored facts
    fact_ids = {f.id for f in facts}
    for c in st.calculations(out.run_id):
        assert set(c.input_fact_ids) <= fact_ids


def test_rounds_are_bounded():
    st = Store(":memory:")
    agent, *_ = make_agent(st)
    out = agent.research(CO, max_rounds=10)
    assert out.rounds <= 5
    out2 = make_agent(Store(":memory:"))[0].research(CO)
    assert out2.rounds <= 3


def test_uploaded_documents_without_search():
    from eia.providers.search import NullSearch
    st = Store(":memory:")
    agent = ResearchAgent(st, get_settings(), search=NullSearch(), llm=NullLLM(), fetcher=FakeFetcher())
    out = agent.research(CO, seed_documents=[SeedDocument("kestrel_ar.html", AR.encode(), "", "text/html")])
    assert out.n_sources == 1 and out.n_facts > 5
    hyps = st.hypotheses(out.run_id)
    assert hyps and all(h.status.value != "proposed" for h in hyps)
    assert any("unavailable" in " ".join(h.limitations) for h in hyps if h.counter_queries)


def test_identity_resolution_is_safe():
    assert resolve("NHPC").status == "resolved"
    amb = resolve("Adani")
    assert amb.status == "ambiguous" and len(amb.candidates) >= 2
    assert resolve("Totally Unknown Widgets").status == "not_found"
