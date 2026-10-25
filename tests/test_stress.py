"""Stress tests: awkward runs must render every page, report and brief without an exception.
All companies, documents and values are fictitious or synthetic; no network."""
import os
import random
from datetime import date

import pytest

from eia.agent import ResearchAgent, SeedDocument
from eia.config import get_settings
from eia.db import Store
from eia.extraction.documents import parse_bytes
from eia.extraction.rules import ExtractionContext, extract_document
from eia.identity import resolve
from eia.providers.direct import DirectFindings
from eia.providers.fetch import FetchResult
from eia.providers.llm import NullLLM
from eia.providers.search import NullSearch, SearchResult
from eia.schema import Company

from .test_ui_smoke import PAGES, FakeSt, run_app  # noqa: F401  (env fixture below mirrors the UI tests)

FIN = """Consolidated Figures in Rs. Crores
Mar 2022   Mar 2023   Mar 2024   Mar 2025
Sales +   1,20,000   1,38,000   1,42,000   1,50,000
Operating Profit   40,000   42,000   41,000   45,000
Interest   9,000   9,800   10,500   11,200
Borrowings +   2,10,000   2,30,000   2,52,000   2,70,000
Cash from Operating Activity +   30,000   28,000   29,500   31,000
Trade Receivables   12,000   14,500   17,800   21,900
"""
COAL = """Coal India style operating review (synthetic)
Raw coal production stood at 700.0 million tonnes in FY2023.
Raw coal production stood at 740.0 million tonnes in FY2024.
Raw coal production stood at 772.0 million tonnes in FY2025.
Coal offtake was 690.0 million tonnes in FY2023. Coal offtake was 730.0 million tonnes in FY2024.
Coal offtake was 750.0 million tonnes in FY2025.
The company targets coal production of 1 billion tonnes by FY2030.
Commissioning of the washery was delayed due to land acquisition issues.
Commissioning of the washery was delayed due to land acquisition issues.
"""
ANN = """On 12 August 2026, Outcome of Board Meeting: approved results.
On 20 July 2026, Credit Rating: the outlook was revised to negative by a rating agency."""


class Fetcher:
    def __init__(self, pages=None, fail=False):
        self.pages, self.fail = pages or {}, fail

    def fetch(self, url):
        if self.fail:
            raise TimeoutError("simulated network timeout")
        for k, body in self.pages.items():
            if k in url:
                return FetchResult(url, True, body.encode(), "text/plain", url)
        return FetchResult(url, False, error="HTTP 404")


class Direct:
    def __init__(self, urls=(), fail=False):
        self.urls, self.fail = urls, fail

    def discover(self, symbol):
        if self.fail:
            raise ConnectionError("simulated outage")
        return DirectFindings(results=[SearchResult(t, u) for t, u in self.urls])


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EIA_DB_PATH", str(tmp_path / "ui.sqlite"))
    monkeypatch.setenv("EIA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EIA_SYNC_JOBS", "1")
    FakeSt.shared_cache.clear()
    return Store(str(tmp_path / "ui.sqlite"))


def _run(store, company, fetcher, direct, seeds=()):
    agent = ResearchAgent(store, get_settings(), search=NullSearch(), llm=NullLLM(), fetcher=fetcher,
                          direct=direct, today=date(2026, 10, 24))
    return agent.research(company, "live", seed_documents=list(seeds), max_rounds=2).run_id


def _scenarios(store):
    out = {}
    # 1. every source fails (network down at the venue)
    out["all_fail"] = _run(store, resolve("NTPC").company, Fetcher(fail=True), Direct(fail=True))
    # 2. a bank: outside Track B, only financial tables
    out["bank"] = _run(store, resolve("HDFC Bank").company, Fetcher({"screener": FIN}),
                       Direct([("Screener", "https://www.screener.in/company/HDFCBANK/consolidated/")]))
    # 3. a coal miner with production, financials, a target, repeated delay mentions and a peer
    out["coal"] = _run(store, resolve("Coal India").company, Fetcher({"/COALINDIA/": FIN, "/NLCINDIA/": FIN, "ops": COAL}),
                       Direct([("Screener", "https://www.screener.in/company/COALINDIA/consolidated/"),
                               ("Operating review", "https://www.coalindia.in/ops.txt")]))
    # 4. only announcements
    out["events_only"] = _run(store, resolve("ONGC").company, Fetcher({"ann": ANN}),
                              Direct([("Announcements", "https://www.nseindia.com/ann.txt")]))
    return out


def test_awkward_runs_render_every_page_report_and_brief(env, monkeypatch):
    from eia import discovery
    from eia.report import build_html, build_markdown
    import importlib.util
    spec = importlib.util.spec_from_file_location("dry_run", os.path.join(os.path.dirname(__file__), "..", "scripts", "dry_run.py"))
    dry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dry)
    runs = _scenarios(env)
    for name, rid in runs.items():
        assert env.get_run(rid).status in ("completed", "partial"), name
        build_markdown(env, rid)
        build_html(env, rid)
        discovery.build(env, rid)
        dry.summarise(env, rid, 1.0)
        for page in PAGES:
            session = {"nav": page, "run_id": rid, "run_select": rid, "pending_run": rid, "mode": "Live research"}
            run_app(monkeypatch, session)  # any exception fails the test
            if page == "Overview":
                session["disc_pick"] = "missing-id"           # a stale pick must fall back, not crash
                run_app(monkeypatch, session)


def test_coal_run_produces_volume_metrics_and_a_single_delay_warning(env):
    runs = _scenarios(env)
    rid = runs["coal"]
    facts = env.facts(rid)
    assert any(f.metric == "coal_production_mt" for f in facts)
    assert any(f.metric == "coal_target_mt" and f.target_year == 2030 for f in facts)
    titles = [h.title for h in env.hypotheses(rid)]
    assert not any(t[0].isdigit() and int(t.split()[0]) > 10 for t in titles), titles


def test_bank_is_flagged_and_gets_no_energy_peers(env):
    runs = _scenarios(env)
    rid = runs["bank"]
    assert not env.get_run(rid).company.eligible and env.peers(rid) == []
    assert not any("leverage" in h.signal_key or "coverage" in h.signal_key for h in env.hypotheses(rid))


def test_network_failure_keeps_a_usable_run(env):
    rid = _scenarios(env)["all_fail"]
    msgs = " ".join(e.message for e in env.events(rid))
    assert env.get_run(rid).status in ("completed", "partial") and ("outage" in msgs or "timeout" in msgs.lower())


@pytest.mark.parametrize("seed", range(25))
def test_random_documents_never_crash_the_extractor(seed):
    rnd = random.Random(seed)
    words = ["revenue", "EBITDA", "capacity", "MW", "₹", "crore", "lakh", "FY2025", "Q1 FY26", "target", "by 2030",
             "borrowings", "(1,234.5)", "-", "%", "Mar 2024", "31.03.2025", "production", "MMT", "BCM", "ckm",
             "consolidated", "standalone", "\t", "\n", "|", "Particulars", "2,69,590.99", "1e9", "NaN", "∞"]
    text = " ".join(rnd.choice(words) for _ in range(rnd.randint(0, 400)))
    for data, ct in ((text.encode(), "text/plain"), (f"<table><tr><td>{text}</td></tr></table>".encode(), "text/html"),
                     (bytes(rnd.getrandbits(8) for _ in range(300)), "application/pdf")):
        doc = parse_bytes(data, ct, "https://example.org/x")
        extract_document(doc, ExtractionContext("r", "s"))
