from eia.extraction.documents import Document, Page
from eia.extraction.llm_extract import extract_with_llm
from eia.extraction.rules import ExtractionContext
from eia.modules.base import Signal
from eia.providers.llm import StaticLLM
from eia.schema import FactStatus, HypothesisStatus, SourceTier, Strength
from eia.verification import grade_evidence, guard_numbers, interpret, update_hypotheses

from .helpers import ctx, fact, src


def pace_signal(f_ids, gap=6000.0):
    return Signal(key="promise_reality:pace:x", module="promise_reality", title="Target at risk", statement="s",
                  severity=0.7, supporting_fact_ids=f_ids, counter_checks=["pipeline_covers_gap"],
                  counter_queries=["q"], params={"gap": gap})


def base_facts():
    return [fact("renewable_capacity_mw", "FY2025", 4000, "MW"),
            fact("renewable_target_mw", "FY2025", 10000, "MW", source_id="s2", fact_type="target", target_year=2030)]


def test_counterevidence_rejects_when_pipeline_covers_gap():
    fs = base_facts() + [fact("capacity_under_construction_mw", "FY2025", 6500, "MW", source_id="s2")]
    h = update_hypotheses(ctx(fs), [pace_signal([f.id for f in fs[:2]])], {}, 2, {"promise_reality:pace:x"}, True)[0]
    assert h.status == HypothesisStatus.rejected
    assert fs[2].id in h.counter_fact_ids
    assert any("covers the remaining gap" in c for c in h.counterarguments)


def test_partial_counterevidence_weakens():
    fs = base_facts() + [fact("capacity_under_construction_mw", "FY2025", 3500, "MW", source_id="s2")]
    h = update_hypotheses(ctx(fs), [pace_signal([f.id for f in fs[:2]])], {}, 2, {"promise_reality:pace:x"}, True)[0]
    assert h.status == HypothesisStatus.weakened


def test_supported_only_after_counter_search():
    fs = base_facts()
    sig = pace_signal([f.id for f in fs])
    h1 = update_hypotheses(ctx(fs), [sig], {}, 1, set(), final=False)[0]
    assert h1.status == HypothesisStatus.proposed  # waiting for counter-evidence search
    h2 = update_hypotheses(ctx(fs), [sig], {sig.key: h1}, 2, {sig.key}, final=False)[0]
    assert h2.status == HypothesisStatus.supported
    assert h2.id == h1.id and len(h2.history) >= 2  # revised, not duplicated


def test_unverified_llm_fact_cannot_be_supported():
    fs = [fact("revenue_cr", "FY2025", 100, "INR_cr", status=FactStatus.unverified),
          fact("revenue_cr", "FY2024", 80, "INR_cr", source_id="s2")]
    sig = Signal(key="k", module="m", title="t", statement="s", supporting_fact_ids=[f.id for f in fs])
    h = update_hypotheses(ctx(fs), [sig], {}, 1, set(), final=True)[0]
    assert h.status == HypothesisStatus.unresolved


def test_insufficient_signal_is_reported_as_such():
    sig = Signal(key="k", module="m", title="t", statement="s", insufficient=True)
    h = update_hypotheses(ctx([]), [sig], {}, 1, set(), final=True)[0]
    assert h.status == HypothesisStatus.insufficient_evidence and h.strength == Strength.insufficient


def test_disappearing_signal_is_rejected_not_kept():
    fs = base_facts()
    sig = pace_signal([f.id for f in fs])
    h1 = update_hypotheses(ctx(fs), [sig], {}, 1, set(), final=False)[0]
    out = update_hypotheses(ctx(fs), [], {sig.key: h1}, 2, set(), final=True)
    assert out[0].status == HypothesisStatus.rejected and "no longer triggered" in out[0].history[-1]


def test_grade_penalises_single_source_and_media():
    c = ctx([fact("revenue_cr", "FY2025", 1, "INR_cr", source_id="m1")], [src("m1", SourceTier.media)])
    g = grade_evidence(c, [c.facts[0].id], set())
    assert g.strength in (Strength.weak, Strength.insufficient)
    assert any("single source" in l for l in g.limitations)
    assert any("No issuer" in l for l in g.limitations)


def test_number_guard():
    assert guard_numbers("Debt rose to 8.3x EBITDA.", "debt is 8.3x EBITDA")
    assert not guard_numbers("Debt will hit 12x by 2027.", "debt is 8.3x EBITDA")


def test_interpretation_with_invented_number_is_discarded():
    fs = base_facts()
    sig = pace_signal([f.id for f in fs])
    c = ctx(fs)
    h = update_hypotheses(c, [sig], {}, 1, set(), True)[0]
    assert interpret(h, c, StaticLLM("This implies a 37% shortfall.")) == ""
    assert interpret(h, c, StaticLLM("Delivery depends on execution; evidence is limited.")) != ""


def test_llm_extraction_drops_ungrounded_proposals():
    doc = Document(pages=[Page(1, "Revenue from operations was ₹ 1,234 crore in FY2025.")])
    llm = StaticLLM('[{"metric":"revenue_cr","value_text":"1,234","unit_text":"crore","period_text":"FY2025",'
                    '"quote":"Revenue from operations was ₹ 1,234 crore in FY2025."},'
                    '{"metric":"revenue_cr","value_text":"9,999","unit_text":"crore","period_text":"FY2025",'
                    '"quote":"Revenue was ₹ 9,999 crore in FY2025."}]')
    facts, dropped = extract_with_llm(doc, ExtractionContext("r", "s1"), llm)
    assert len(facts) == 1 and dropped == 1
    assert facts[0].value == 1234 and facts[0].period == "FY2025" and facts[0].extraction_method == "llm"
