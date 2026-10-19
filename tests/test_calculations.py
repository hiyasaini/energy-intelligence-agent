import math

import pytest

from eia.calculations import Calculator, Point, build_series
from eia.metrics import parse_number, unit_factor
from eia.periods import parse_asof, parse_period, parse_target_year
from eia.schema import Scope, SourceTier

from .helpers import annual, fact, target


def P(period, value, fid="f", scope="consolidated", unit="INR_cr"):
    return Point(period, value, fid, scope, unit)


def test_growth_and_inputs_are_traceable():
    c = Calculator("r", "m")
    r = c.growth("rev", P("FY2024", 100, "a"), P("FY2025", 125, "b"))
    assert r.result == pytest.approx(25.0)
    assert r.input_fact_ids == ["a", "b"] and r.status == "ok" and r.unit == "%"


def test_growth_zero_base_is_insufficient_not_infinite():
    c = Calculator("r", "m")
    r = c.growth("rev", P("FY2024", 0), P("FY2025", 10))
    assert r.result is None and r.status == "insufficient_data"


def test_growth_from_negative_base_is_not_reported():
    c = Calculator("r", "m")
    r = c.growth("cfo", P("FY2024", -57), P("FY2025", 241))
    assert r.result is None and "negative base" in r.notes


def test_cagr():
    c = Calculator("r", "m")
    from eia.calculations import Series
    s = Series("revenue_cr", "INR_cr", [P("FY2021", 100, "a"), P("FY2022", 110), P("FY2024", 133.1, "c")])
    r = c.cagr("cagr", s)
    assert r.result == pytest.approx(10.0, rel=1e-6)
    assert r.inputs["years"] == 3 and r.input_fact_ids == ["a", "c"]


def test_ratio_period_mismatch_is_incompatible():
    c = Calculator("r", "m")
    r = c.ratio("lev", P("FY2024", 10), P("FY2025", 2))
    assert r.status == "incompatible" and r.result is None


def test_ratio_scope_mismatch_warns():
    c = Calculator("r", "m")
    r = c.ratio("lev", P("FY2025", 10, scope="consolidated"), P("FY2025", 2, scope="standalone"))
    assert r.result == 5 and r.status == "warning"


def test_difference_unit_mismatch():
    c = Calculator("r", "m")
    r = c.difference("d", P("FY2025", 10, unit="MW"), P("FY2025", 2, unit="MU"))
    assert r.status == "incompatible" and r.result is None


def test_change_across_periods():
    c = Calculator("r", "m")
    r = c.change("add", P("FY2024", 100, "a", unit="MW"), P("FY2025", 160, "b", unit="MW"))
    assert r.result == 60 and r.input_fact_ids == ["a", "b"]
    bad = c.change("add", P("FY2025", 100, unit="MW"), P("FY2024", 160, unit="MW"))
    assert bad.status == "incompatible"


def test_target_progress_and_required_rate():
    c = Calculator("r", "m")
    t = target("renewable_target_mw", 10000, "MW", 2030)
    cur = P("FY2025", 4000, "cur", unit="MW")
    out = c.target_progress("t", t, cur, None)
    assert out[0].result == pytest.approx(40.0)
    assert out[1].result == pytest.approx(1200.0)  # (10000-4000)/5 years


def test_correlation_needs_enough_periods():
    c = Calculator("r", "m")
    from eia.calculations import Series
    a = Series("x", "MW", [P(f"FY{y}", y, unit="MW") for y in range(2021, 2025)])
    r = c.correlation("r", a, a)
    assert r.status == "insufficient_data"


def test_nonfinite_results_suppressed():
    c = Calculator("r", "m")
    r = c._rec(name="x", formula="x", result=math.inf)
    assert r.result is None and r.status == "insufficient_data"


@pytest.mark.parametrize("s,v", [("1,23,456.7", 123456.7), ("(1,234)", -1234), ("-12.5", -12.5), ("abc", None)])
def test_parse_number_indian_formats(s, v):
    assert parse_number(s) == v


def test_units_normalise_and_never_convert_foreign_currency():
    assert unit_factor("GW", "power") == (1000.0, "MW")
    assert unit_factor("lakh crore", "money") == (1e5, "INR_cr")
    assert unit_factor("BU", "energy") == (1000.0, "MU")
    assert unit_factor("US$ million", "money") is None
    assert unit_factor("MW", "money") is None


def test_period_parsing():
    assert parse_period("revenue for FY 2023-24") == "FY2024"
    assert parse_period("Q2 FY25 results") == "Q2FY2025"
    assert parse_period("quarter ended 30 June 2025") == "Q1FY2026"
    assert parse_asof("as on 31 March 2025") == "FY2025"
    assert parse_target_year("target of 50 GW by 2030") == 2030
    assert parse_target_year("by FY2029-30") == 2030


def test_build_series_prefers_verified_and_dominant_scope():
    facts = annual("revenue_cr", "INR_cr", {2024: 100, 2025: 120})
    facts.append(fact("revenue_cr", "FY2025", 90, "INR_cr", scope=Scope.standalone))
    s = build_series(facts, "revenue_cr", {"s1": SourceTier.company})
    assert s.get("FY2025").value == 120  # consolidated dominates
    assert not s.conflicts  # different scopes are not a contradiction
