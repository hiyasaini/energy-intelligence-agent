"""Regression tests on transcribed public disclosures (validation/). Fully offline.

These companies were used to find and fix generic format gaps, so they are regression fixtures now, not
'unseen' tests. Expected values come from the transcriptions, not from the application.
"""
from pathlib import Path

import pytest

from eia.agent import ResearchAgent, SeedDocument
from eia.config import get_settings
from eia.db import Store
from eia.identity import resolve
from eia.providers.llm import NullLLM
from eia.providers.search import NullSearch
from eia.schema import HypothesisStatus, SourceTier

V = Path(__file__).resolve().parent.parent / "validation"

SETS = {
    "KPIGREEN": [("kpigreen/ar_fy2025_nse.txt", "https://nsearchives.nseindia.com/annual_reports/AR_KPIGREEN_2024_2025.pdf"),
                 ("kpigreen/results_fy2026_consolidated_nse.txt", "https://nsearchives.nseindia.com/corporate/ixbrl/kpi_c.html"),
                 ("kpigreen/results_fy2026_standalone_nse.txt", "https://nsearchives.nseindia.com/corporate/ixbrl/kpi_s.html"),
                 ("kpigreen/screener_consolidated.txt", "https://www.screener.in/company/KPIGREEN/consolidated/")],
    "TORNTPOWER": [("torrentpower/results_fy2026_consolidated_nse.txt", "https://nsearchives.nseindia.com/corporate/ixbrl/tp.html"),
                   ("torrentpower/investor_presentation_q1fy27_nse.txt", "https://nsearchives.nseindia.com/corporate/TP_IP.pdf"),
                   ("torrentpower/screener_consolidated.txt", "https://www.screener.in/company/TORNTPOWER/consolidated/")],
    "NHPC": [("nhpc/results_fy2026_consolidated_nse.txt", "https://nsearchives.nseindia.com/corporate/ixbrl/nhpc.html"),
             ("nhpc/screener_consolidated.txt", "https://www.screener.in/company/NHPC/consolidated/")],
}


def test_regression_runs_are_offline():
    """Module fixtures run before per-test fixtures: the session itself must be offline."""
    s = get_settings()
    assert not s.direct_sources and s.search_provider == "none"


@pytest.fixture(scope="module")
def runs():
    out = {}
    for sym, docs in SETS.items():
        st = Store(":memory:")
        seeds = [SeedDocument(Path(p).name, (V / p).read_bytes(), url, "text/plain") for p, url in docs]
        o = ResearchAgent(st, get_settings(), search=NullSearch(), llm=NullLLM()).research(
            resolve(sym).company, seed_documents=seeds)
        out[sym] = (st, o)
    return out


def val(st, run_id, metric, period, tier=None):
    srcs = {s.id: s for s in st.sources(run_id)}
    return sorted(round(f.value, 2) for f in st.facts(run_id) if f.metric == metric and f.period == period
                  and (tier is None or srcs[f.source_id].tier == tier) and f.scope.value != "standalone")


def test_lakh_filing_converted_and_borrowings_summed(runs):
    st, o = runs["KPIGREEN"]
    assert val(st, o.run_id, "revenue_cr", "FY2026", SourceTier.exchange) == [2695.91]
    assert val(st, o.run_id, "gross_debt_cr", "FY2026", SourceTier.exchange) == [4531.95]
    assert val(st, o.run_id, "capacity_target_mw", "FY2025") == [10000.0]


def test_ratio_rows_never_become_amounts(runs):
    for sym, (st, o) in runs.items():
        for f in st.facts(o.run_id):
            if f.unit == "INR_cr" and f.metric in ("ebitda_cr", "gross_debt_cr", "net_debt_cr", "equity_cr"):
                assert abs(f.value) >= 10, (sym, f.metric, f.period, f.value, f.label)


def test_cross_source_conflict_is_surfaced(runs):
    from eia.views import contradictions
    st, o = runs["KPIGREEN"]
    assert any(c["metric"].startswith("Gross debt") and c["period"] == "FY2026" for c in contradictions(st, o.run_id))


def test_undated_columns_are_not_guessed(runs):
    st, o = runs["NHPC"]
    filing = [s for s in st.sources(o.run_id) if "nhpc.html" in s.url][0]
    assert not [f for f in st.facts(o.run_id) if f.source_id == filing.id]


def test_aggregator_only_evidence_is_never_supported(runs):
    st, o = runs["NHPC"]
    hyps = st.hypotheses(o.run_id)
    assert hyps and all(h.status != HypothesisStatus.supported for h in hyps)


def test_presentation_short_span_headers(runs):
    st, o = runs["TORNTPOWER"]
    assert val(st, o.run_id, "revenue_cr", "Q1FY2027", SourceTier.exchange) == [8124.0]
    assert val(st, o.run_id, "ebitda_cr", "FY2022", SourceTier.exchange) == [3826.0]
