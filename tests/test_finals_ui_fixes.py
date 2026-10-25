"""Regression tests for the finals-eve fixes (capex scale, readable module notes)."""

from eia import sanity
from eia.calculations import Point, Series


def _series(metric, vals):
    return Series(metric, "INR_cr", [Point(p, v, f"f{i}", "consolidated", "INR_cr") for i, (p, v) in enumerate(vals)])


def test_capex_far_too_small_for_revenue_is_held_out():
    s = _series("capex_cr", [("FY2025", 900.0), ("FY2026", 1200.0)])
    out = sanity.apply("capex_cr", s, "oil_gas", lambda p: 780000.0)
    assert not out.points and len(out.excluded) == 2


def test_real_capex_and_lender_capex_are_kept():
    s = _series("capex_cr", [("FY2025", 30000.0), ("FY2026", 32000.0)])
    assert len(sanity.apply("capex_cr", s, "oil_gas", lambda p: 780000.0).points) == 2
    s = _series("capex_cr", [("FY2026", 50.0)])
    assert len(sanity.apply("capex_cr", s, "lender", lambda p: 90000.0).points) == 1


def test_module_notes_use_labels_and_collapse_old_years():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    src = (root / "app.py").read_text(encoding="utf-8")
    start = src.index("def readable_notes")
    end = src.index("def page_module")
    ns = {}
    import re
    from eia.metrics import METRICS
    exec(src[start:end], {"re": re, "METRICS": METRICS}, ns)
    notes = ["gross_debt_cr FY2015: more than 10 years older than the latest figure; not used in trends.",
             "pat_cr: FY2027 not yet ended; figures for it are not used as actuals."]
    out = ns["readable_notes"](notes)
    assert not any("_cr" in n for n in out)
    assert out[-1].startswith("Figures more than 10 years older")
