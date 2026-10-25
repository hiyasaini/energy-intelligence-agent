"""Price-led vs volume-led growth (fictitious values)."""
from eia.modules import green_growth

from .helpers import annual, ctx


def _keys(res):
    return {s.key.split(":")[1] for s in res.signals}


def test_price_led_growth_for_a_coal_miner():
    facts = annual("coal_offtake_mt", "Mt", {2021: 600, 2022: 630, 2023: 660, 2024: 690}) + \
        annual("revenue_cr", "INR_cr", {2021: 100000, 2022: 125000, 2023: 150000, 2024: 180000})
    res = green_growth.run(ctx(facts))
    assert "price_led" in _keys(res)
    sig = next(s for s in res.signals if "price_led" in s.key)
    assert "sector_wide" in sig.counter_checks and sig.calc_ids
    assert "Installed / operating capacity" not in res.missing  # not a power company


def test_falling_realisations():
    facts = annual("generation_mu", "MU", {2021: 1000, 2022: 1300, 2023: 1700, 2024: 2200}) + \
        annual("revenue_cr", "INR_cr", {2021: 500, 2022: 520, 2023: 540, 2024: 560})
    assert "realisation_down" in _keys(green_growth.run(ctx(facts)))


def test_volume_and_revenue_in_step_raise_nothing():
    facts = annual("oil_gas_production_mtoe", "Mtoe", {2021: 40, 2022: 42, 2023: 44, 2024: 46}) + \
        annual("revenue_cr", "INR_cr", {2021: 400, 2022: 420, 2023: 445, 2024: 465})
    assert not {"price_led", "realisation_down"} & _keys(green_growth.run(ctx(facts)))


def test_many_mentions_of_one_kind_of_event_are_one_warning():
    from eia.modules import hidden_risk
    from eia.schema import FactType
    from .helpers import fact
    evs = [fact("event", "FY2025", 1.0, "count", passage=f"Commissioning of unit {i} was delayed due to land issues.",
                fact_type=FactType.event, event_category="delay") for i in range(40)]
    risk = [s for s in green_growth.run(ctx(annual("generation_mu", "MU", {2021: 1000, 2022: 1300, 2023: 1700, 2024: 2200})
                                            + annual("revenue_cr", "INR_cr", {2021: 500, 2022: 520, 2023: 540, 2024: 560}))).signals]
    res = hidden_risk.run(ctx(evs), risk)
    comp = [s for s in res.signals if "composite" in s.key]
    assert comp and "(2 signals" in comp[0].title
