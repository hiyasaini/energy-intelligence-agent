"""The research assistant answers only from the run's own evidence (synthetic demo data, no network)."""
import re

from eia import assistant
from eia.config import get_settings
from eia.db import Store
from eia.demo import run_demo


def _run(tmp_path):
    store = Store(str(tmp_path / "a.sqlite"))
    return store, run_demo(store, get_settings()).run_id


def test_briefing_names_the_lead_discovery_with_its_grade(tmp_path):
    store, rid = _run(tmp_path)
    text = assistant.briefing(store, rid).text
    assert "lead discovery" in text and re.search(r"(Supported|Unresolved|Weakened)", text)


def test_answers_quote_findings_and_reported_figures(tmp_path):
    store, rid = _run(tmp_path)
    a = assistant.answer(store, rid, "How is debt moving?")
    assert a.finding_ids and "Gross debt" in a.text and "FY" in a.text


def test_every_number_in_an_answer_comes_from_the_run(tmp_path):
    store, rid = _run(tmp_path)
    corpus = " ".join([h.title + " " + h.statement for h in store.hypotheses(rid)] +
                      [f"{f.value:,.0f} {f.value:,.1f} {f.period}" for f in store.facts(rid) if f.value is not None])
    text = assistant.answer(store, rid, "What about revenue and EBITDA?").text
    for n in re.findall(r"\d[\d,]*", re.sub(r"[+-]?\d+\.\d%", "", text)):
        assert n in corpus, n


def test_unknown_questions_are_not_guessed(tmp_path):
    store, rid = _run(tmp_path)
    assert "will not guess" in assistant.answer(store, rid, "weather in Paris tomorrow").text
