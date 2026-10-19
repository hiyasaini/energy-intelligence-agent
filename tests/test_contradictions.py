from eia.calculations import build_series
from eia.schema import HypothesisStatus, RelLabel, Scope, SourceTier
from eia.verification import update_hypotheses

from .helpers import annual, ctx, fact, src


def test_conflicting_values_are_detected_and_labelled():
    facts = annual("revenue_cr", "INR_cr", {2024: 100, 2025: 120})
    facts.append(fact("revenue_cr", "FY2025", 130, "INR_cr", source_id="s2"))
    s = build_series(facts, "revenue_cr", {"s1": SourceTier.company, "s2": SourceTier.media})
    assert len(s.conflicts) == 1 and s.conflicts[0].period == "FY2025"
    c = ctx(facts, [src("s1"), src("s2", SourceTier.media)])
    rels = c.conflict_relationships(c.series("revenue_cr"), "x")
    assert rels and rels[0].label == RelLabel.contradictory


def test_small_differences_within_tolerance_are_not_conflicts():
    facts = annual("revenue_cr", "INR_cr", {2025: 100.0})
    facts.append(fact("revenue_cr", "FY2025", 101.0, "INR_cr", source_id="s2"))
    assert not build_series(facts, "revenue_cr", {}).conflicts


def test_issuer_source_preferred_over_media():
    facts = [fact("revenue_cr", "FY2025", 130, "INR_cr", source_id="s2"),
             fact("revenue_cr", "FY2025", 120, "INR_cr", source_id="s1")]
    s = build_series(facts, "revenue_cr", {"s1": SourceTier.company, "s2": SourceTier.media})
    assert s.get("FY2025").value == 120


def test_finding_built_on_conflicted_input_is_unresolved():
    from eia.modules.base import Signal
    good = fact("pat_cr", "FY2025", 50, "INR_cr")
    conflicted = fact("revenue_cr", "FY2025", 120, "INR_cr")
    other = fact("revenue_cr", "FY2025", 140, "INR_cr", source_id="s2")
    c = ctx([good, conflicted, other])
    sig = Signal(key="k", module="early_warning", title="t", statement="s", severity=0.6,
                 supporting_fact_ids=[good.id, conflicted.id], counter_queries=[])
    h = update_hypotheses(c, [sig], {}, 1, set(), final=True)[0]
    assert h.status == HypothesisStatus.unresolved
    assert any("conflict" in l for l in h.limitations)
    clean = Signal(key="k2", module="early_warning", title="t", statement="s", severity=0.6,
                   supporting_fact_ids=[good.id], counter_queries=[])
    h2 = update_hypotheses(c, [clean], {}, 1, set(), final=True)[0]
    assert h2.status != HypothesisStatus.unresolved or h2.strength.value == "weak"


def test_mixed_scope_series_warns():
    facts = [fact("revenue_cr", "FY2024", 100, "INR_cr", scope=Scope.standalone),
             fact("revenue_cr", "FY2025", 150, "INR_cr", scope=Scope.consolidated)]
    s = build_series(facts, "revenue_cr", {})
    assert any("mixes consolidated and standalone" in w for w in s.warnings)
