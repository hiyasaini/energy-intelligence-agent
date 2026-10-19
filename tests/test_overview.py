"""Overview panels: every number derives from stored facts/findings; missing data stays missing."""
import pytest

from eia import views
from eia.db import Store
from eia.demo import run_demo
from eia.providers.market import parse_chart

from .helpers import CO


@pytest.fixture(scope="module")
def demo():
    st = Store(":memory:")
    return st, run_demo(st).run_id


def test_energy_mix_sums_reported_sources(demo):
    st, rid = demo
    mix = views.energy_mix(st, rid)
    assert mix["period"] == "FY2025" and mix["total"] == 4300
    assert {i["source"]: i["mw"] for i in mix["items"]} == {"Solar": 2650, "Wind": 1350, "Hydro": 300}
    assert abs(sum(i["share"] for i in mix["items"]) - 100) < 1e-6


def test_esg_intensity_change_from_reported_figures(demo):
    st, rid = demo
    esg = views.esg_series(st, rid)
    assert [p["value"] for p in esg["intensity"]] == [0.021, 0.019, 0.017, 0.016, 0.014]
    assert esg["intensity_change_pct"] == pytest.approx((0.014 - 0.021) / 0.021 * 100)


def test_trend_yoy_and_progress(demo):
    st, rid = demo
    t = views.trend(st, rid, "revenue_cr")
    assert t[0]["yoy"] is None and t[1]["yoy"] == pytest.approx((3050 - 2610) / 2610 * 100)
    steps = views.research_progress(st, rid)
    assert all(s["done"] for s in steps)
    assert views.evidence_confidence(st, rid)["total"] > 0
    assert views.risk_level(st, rid)["level"] in ("Low", "Medium", "High")


def test_empty_run_has_no_invented_values():
    st = Store(":memory:")
    from eia.agent import ResearchAgent
    from eia.providers.llm import NullLLM
    from eia.providers.search import NullSearch
    rid = ResearchAgent(st, search=NullSearch(), llm=NullLLM()).research(CO, max_rounds=1).run_id
    assert views.energy_mix(st, rid)["items"] == []
    assert views.esg_series(st, rid)["intensity"] == []
    assert views.trend(st, rid, "revenue_cr") == []
    assert views.capacity_points(st, rid)[1] == []
    assert views.evidence_confidence(st, rid)["pct"] is None
    assert views.outlook(st, rid)["label"] == "Insufficient evidence"
    assert views.risk_level(st, rid)["level"] == "Insufficient evidence"


def test_market_chart_parsing_and_errors():
    data = {"chart": {"result": [{"meta": {"regularMarketPrice": 350.5, "currency": "INR", "regularMarketTime": 1760000000},
                                  "timestamp": [1759000000, 1759600000],
                                  "indicators": {"quote": [{"close": [340.0, None]}]}}]}}
    q = parse_chart("NTPC.NS", data)
    assert q.ok and q.price == 350.5 and q.closes == [340.0]
    assert parse_chart("X.NS", {"chart": {"result": []}}).error


def test_relative_performance_rebases_to_zero():
    from eia.providers.market import MarketQuote, relative_performance
    s = MarketQuote("A", dates=["2026-01-01", "2026-02-01", "2026-03-01"], closes=[100, 110, 120])
    i = MarketQuote("I", dates=["2026-01-01", "2026-03-01"], closes=[200, 210])
    rp = relative_performance(s, i)
    assert rp["dates"] == ["2026-01-01", "2026-03-01"]
    assert rp["stock"] == pytest.approx([0.0, 20.0]) and rp["index"] == pytest.approx([0.0, 5.0])


def test_day_change_ignores_repeated_live_bar_and_weekly_bars():
    day = 86400
    t0 = 1760000000  # the quote's own day
    meta = {"regularMarketPrice": 130.38, "regularMarketTime": t0, "dataGranularity": "1d"}
    # Yahoo repeats the live bar: two closes on the quote's day, the real previous close a day earlier
    data = {"chart": {"result": [{"meta": meta, "timestamp": [t0 - day, t0 - 60, t0],
                                  "indicators": {"quote": [{"close": [128.0, 130.38, 130.38]}]}}]}}
    q = parse_chart("IOC.NS", data)
    assert q.change_pct == pytest.approx((130.38 - 128.0) / 128.0 * 100)
    assert len(q.dates) == 2
    weekly = {"chart": {"result": [{"meta": {**meta, "dataGranularity": "1wk"}, "timestamp": [t0 - 7 * day, t0],
                                    "indicators": {"quote": [{"close": [120.0, 130.38]}]}}]}}
    assert parse_chart("IOC.NS", weekly).change_pct is None  # a weekly move is not a day change

