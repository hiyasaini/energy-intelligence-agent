"""Peer comparison: peer choice by line of business, comparable figures, and the sector-wide counter-check.
All companies and values are fictitious; no network."""
from datetime import date

from eia.agent import ResearchAgent
from eia.config import get_settings
from eia.db import Store
from eia.modules.base import Signal
from eia.peers import PeerProfile, choose_peers, compare, family, profile
from eia.providers.fetch import FetchResult
from eia.providers.llm import NullLLM
from eia.providers.search import NullSearch
from eia.schema import Company
from eia.verification import evaluate_signal

from .helpers import annual, ctx

REG = [Company(name="Kestrel Hydro Power Ltd", nse="KESTREL", segment="hydro generation"),
       Company(name="Kestrel Green Ltd", nse="KESTRELG", segment="renewable generation"),
       Company(name="Osprey Power Ltd", nse="OSPREY", segment="thermal+renewable generation"),
       Company(name="Harrier Energy Ltd", nse="HARRIER", segment="renewable generation"),
       Company(name="Merlin Oil Ltd", nse="MERLIN", segment="oil & gas upstream"),
       Company(name="Falcon Grid Ltd", nse="FALCON", segment="transmission"),
       Company(name="Kite Coal Ltd", nse="KITE", segment="coal mining")]


def test_peers_share_the_line_of_business_and_skip_the_group():
    co = REG[0]
    assert [p.nse for p in choose_peers(co, REG)] == ["OSPREY", "HARRIER"]   # not its own group (Kestrel Green)
    assert family("oil & gas upstream") == "oil_gas" and family("coal mining") == "coal"
    assert family("transmission") == "transmission" and family("") == ""
    assert choose_peers(Company(name="Unknown Ltd", nse="UNK"), REG) == []


def test_profile_computes_comparable_ratios():
    facts = annual("revenue_cr", "INR_cr", {2022: 100, 2023: 110, 2024: 121, 2025: 133.1}) + \
        annual("ebitda_cr", "INR_cr", {2022: 40, 2023: 44, 2024: 48.4, 2025: 53.24}) + \
        annual("gross_debt_cr", "INR_cr", {2025: 266.2}) + annual("finance_cost_cr", "INR_cr", {2025: 13.31})
    p = profile(facts)
    assert round(p["revenue_cagr"], 1) == 10.0 and round(p["debt_to_ebitda"], 1) == 5.0
    assert round(p["coverage"], 1) == 4.0 and round(p["ebitda_margin"], 1) == 40.0


def _peer(sym, **m):
    return PeerProfile(sym, f"{sym.title()} Ltd", "", m)


def test_compare_marks_in_line_and_outlier():
    peers = [_peer("A", debt_to_ebitda=5.5), _peer("B", debt_to_ebitda=6.0), _peer("C", debt_to_ebitda=6.5)]
    assert compare("capital_cash:leverage", {"debt_to_ebitda": 6.2}, peers)["verdict"] == "in_line"
    assert compare("capital_cash:leverage", {"debt_to_ebitda": 9.0}, peers)["verdict"] == "outlier"
    assert compare("capital_cash:leverage", {"debt_to_ebitda": 9.0}, peers[:1]) is None  # too few peers
    assert compare("promise_reality:pace", {"debt_to_ebitda": 9.0}, peers) is None      # not comparable


def _leverage_signal(c):
    return Signal(key="capital_cash:leverage", module="capital_cash", title="High leverage", statement="s",
                  severity=0.6, supporting_fact_ids=[f.id for f in c.facts][:2], counter_checks=[])


def test_sector_wide_check_becomes_the_counterargument():
    facts = annual("gross_debt_cr", "INR_cr", {2024: 600, 2025: 620}) + annual("ebitda_cr", "INR_cr", {2024: 100, 2025: 100})
    c = ctx(facts)
    c.peers = [_peer("A", debt_to_ebitda=5.8), _peer("B", debt_to_ebitda=6.4)]
    ev = evaluate_signal(c, _leverage_signal(c), set(), True, True)
    chk = [x for x in ev["checks"] if x["check"] == "sector_wide"][0]
    assert chk["effect"] == "opposes" and "sector-wide" in chk["note"] and "similar or weaker" in chk["note"]
    assert ev["status"].value != "rejected"           # sector-wide is context, not a refutation


def test_outlier_check_supports_the_finding():
    facts = annual("gross_debt_cr", "INR_cr", {2024: 900, 2025: 950}) + annual("ebitda_cr", "INR_cr", {2024: 100, 2025: 100})
    c = ctx(facts)
    c.peers = [_peer("A", debt_to_ebitda=3.0), _peer("B", debt_to_ebitda=3.5)]
    chk = [x for x in evaluate_signal(c, _leverage_signal(c), set(), True, True)["checks"]
           if x["check"] == "sector_wide"][0]
    assert chk["effect"] == "supports" and "stands out" in chk["note"]


PEER_PAGE = b"""<html><body><p>Consolidated Figures in Rs. Crores</p><table>
<tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th></tr>
<tr><td>Sales +</td><td>500</td><td>550</td><td>605</td></tr>
<tr><td>Operating Profit</td><td>200</td><td>220</td><td>242</td></tr>
<tr><td>Interest</td><td>40</td><td>44</td><td>48</td></tr>
<tr><td>Borrowings +</td><td>1,000</td><td>1,100</td><td>1,210</td></tr></table></body></html>"""


class PeerFetcher:
    def fetch(self, url):
        if "/OSPREY/" in url or "/HARRIER/" in url:
            return FetchResult(url, True, PEER_PAGE, "text/html", url)
        return FetchResult(url, False, error="HTTP 404")


class NoDirect:
    def discover(self, symbol):
        from eia.providers.direct import DirectFindings
        return DirectFindings()


def test_live_run_collects_and_stores_peers(monkeypatch):
    monkeypatch.setattr("eia.identity.load_registry", lambda *a, **k: REG)
    st = Store(":memory:")
    out = ResearchAgent(st, get_settings(), search=NullSearch(), llm=NullLLM(), fetcher=PeerFetcher(),
                        direct=NoDirect(), today=date(2026, 9, 1)).research(REG[0], max_rounds=1)
    peers = st.peers(out.run_id)
    assert [p["symbol"] for p in peers] == ["OSPREY", "HARRIER"]
    assert round(peers[0]["metrics"]["debt_to_ebitda"], 1) == 5.0 and not peers[0]["error"]
    assert not any(f.source_id.startswith("peer:") for f in st.facts(out.run_id))  # peers never mix into company facts
    assert "Peer comparison:" in " ".join(e.message for e in st.events(out.run_id))


def test_peer_table_for_the_discovery(monkeypatch):
    from eia.discovery import peer_table
    monkeypatch.setattr("eia.identity.load_registry", lambda *a, **k: REG)
    st = Store(":memory:")
    out = ResearchAgent(st, get_settings(), search=NullSearch(), llm=NullLLM(), fetcher=PeerFetcher(),
                        direct=NoDirect(), today=date(2026, 9, 1)).research(REG[0], max_rounds=1)
    t = peer_table(st, out.run_id)
    assert t["symbols"] == ["OSPREY", "HARRIER"]
    lev = next(r for r in t["rows"] if r["metric"].startswith("Debt / EBITDA"))
    assert [round(v, 1) for v in lev["peers"]] == [5.0, 5.0]


def test_no_peer_table_without_peers():
    from eia.discovery import peer_table
    st = Store(":memory:")
    assert peer_table(st, "missing-run") is None


def test_generation_lag_is_not_compared_on_revenue():
    from eia.peers import comparable
    assert comparable("green_growth:lag:generation_mu") is None
    assert comparable("green_growth:lag:revenue_cr")[0] == "revenue_cagr"
