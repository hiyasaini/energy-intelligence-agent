"""Plausibility guards found during live runs (fictitious values reproducing the patterns)."""
from eia.calculations import build_series

from .helpers import annual, fact


def test_misread_old_year_is_held_out_of_trends():
    facts = annual("revenue_cr", "INR_cr", {2001: 900, 2022: 100, 2023: 110, 2024: 125, 2025: 130, 2026: 140})
    s = build_series(facts, "revenue_cr", {})
    assert s.periods[0] == "FY2022"
    assert s.excluded and s.excluded[0]["period"] == "FY2001"


def test_isolated_old_point_is_held_out():
    facts = annual("revenue_cr", "INR_cr", {2014: 50, 2022: 100, 2023: 110, 2024: 120})
    s = build_series(facts, "revenue_cr", {})
    assert s.periods == ["FY2022", "FY2023", "FY2024"]


def test_part_year_value_needs_corroboration():
    facts = annual("revenue_cr", "INR_cr", {2022: 1300, 2023: 1760, 2024: 1780, 2025: 170})
    s = build_series(facts, "revenue_cr", {})
    assert "FY2025" not in s.periods
    assert any("single source" in w for w in s.warnings)


def test_jump_confirmed_by_a_second_source_is_kept():
    facts = annual("finance_cost_cr", "INR_cr", {2022: 10, 2023: 11, 2024: 12, 2025: 300})
    facts.append(fact("finance_cost_cr", "FY2025", 301, "INR_cr", source_id="s2"))
    s = build_series(facts, "finance_cost_cr", {})
    assert s.get("FY2025") is not None


def test_signed_metrics_are_not_screened():
    facts = annual("pat_cr", "INR_cr", {2022: 100, 2023: 5, 2024: 120})
    assert len(build_series(facts, "pat_cr", {})) == 3


def test_normal_growth_is_untouched():
    facts = annual("revenue_cr", "INR_cr", {2021: 100, 2022: 180, 2023: 320, 2024: 560})
    assert len(build_series(facts, "revenue_cr", {})) == 4
