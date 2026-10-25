"""Fixes for patterns seen in the live dry run (fictitious values and sentences reproducing them)."""
from eia.calculations import build_series
from eia.extraction.documents import Document, Page
from eia.extraction.rules import ExtractionContext, _scope_of, extract_document, extract_events, extract_from_sentence
from eia.modules import early_warning, green_growth, promise_reality
from eia.schema import Scope

from .helpers import annual, ctx, fact, target


def test_wrong_scale_figure_falls_back_to_another_source_for_the_same_period():
    facts = annual("revenue_cr", "INR_cr", {2022: 1300, 2023: 1760, 2024: 1780}, source_id="tables")
    facts.append(fact("revenue_cr", "FY2025", 180, "INR_cr", source_id="report"))        # preferred, wrong scale
    facts.append(fact("revenue_cr", "FY2025", 1850, "INR_cr", source_id="tables", scope=Scope.unknown))
    s = build_series(facts, "revenue_cr", {})
    assert s.get("FY2025").value == 1850 and s.excluded


def test_signed_metric_out_of_scale_uses_the_in_scale_source():
    facts = annual("cfo_cr", "INR_cr", {2022: 300, 2023: 320, 2024: 310}, source_id="tables")
    facts.append(fact("cfo_cr", "FY2025", 3, "INR_cr", source_id="report"))
    facts.append(fact("cfo_cr", "FY2025", 330, "INR_cr", source_id="tables", scope=Scope.unknown))
    assert build_series(facts, "cfo_cr", {}).get("FY2025").value == 330


def test_link_to_the_other_view_does_not_set_scope():
    assert _scope_of("Consolidated Figures in Rs. Crores / View Standalone") == Scope.consolidated
    assert _scope_of("Balance Sheet  View Standalone") == Scope.unknown
    doc = Document(pages=[Page(1, "Balance Sheet  View Standalone\nFigures in Rs. Crores\nMar 2024   Mar 2025\nBorrowings +   100   120\n")])
    facts = extract_document(doc, ExtractionContext("r", "s", scope_hint="https://x.example/company/ABC/consolidated/"))
    assert facts and all(f.scope == Scope.consolidated for f in facts)


def test_national_goal_quoted_in_a_report_is_not_a_company_target():
    c = ExtractionContext("r", "s", "FY2025")
    nat = "India plans to add more than 80 GW of new coal capacity by 2034 and 500 GW of RE capacity by 2030."
    own = "The company has set a target of 149 GW of total installed capacity by 2032."
    assert not [f for f in extract_from_sentence(nat, c, 1, Scope.unknown) if f.fact_type.value == "target"]
    assert [f for f in extract_from_sentence(own, c, 1, Scope.unknown) if f.fact_type.value == "target"]


def test_target_far_above_current_level_is_held_out():
    facts = annual("installed_capacity_mw", "MW", {2022: 70000, 2023: 74000, 2024: 78000, 2025: 82000})
    facts.append(target("capacity_target_mw", 500000, "MW", 2030))
    res = promise_reality.run(ctx(facts))
    assert not any("pace" in s.key or "build" in s.title for s in res.signals)
    assert any("national" in n for n in res.notes)


def test_renewable_share_above_100_percent_is_not_reported():
    facts = annual("installed_capacity_mw", "MW", {2023: 1000, 2024: 1100})
    facts += annual("renewable_capacity_mw", "MW", {2023: 9000, 2024: 9500})
    res = green_growth.run(ctx(facts))
    assert not any(r.get("metric") == "Renewable share of capacity" for r in res.rows)


def test_accounting_and_hypothetical_delays_are_not_events():
    c = ExtractionContext("r", "s", "FY2025")
    noise = ["Deferred tax liabilities increased in FY2025.",
             "Delayed payment surcharge was levied on the distribution company in FY2025.",
             "Any delay in project commissioning could adversely affect revenue in FY2025."]
    for t in noise:
        assert not extract_events(t, c, 1, Scope.unknown), t
    assert extract_events("Commissioning of Unit 2 was delayed due to land acquisition in FY2025.", c, 1, Scope.unknown)


def test_extreme_year_on_year_growth_is_not_a_signal():
    facts = annual("pat_cr", "INR_cr", {2022: 100, 2023: 2, 2024: 150})
    res = early_warning.run(ctx(facts))
    assert not any(":pat_cr:" in s.key for s in res.signals)


# ---- dry run 3 ------------------------------------------------------------------------------------------

def test_full_history_table_beats_single_period_mentions():
    from datetime import date
    facts = annual("ebitda_cr", "INR_cr", {y: 1000 + 50 * i for i, y in enumerate(range(2016, 2027))}, source_id="tables")
    facts.append(fact("ebitda_cr", "FY2026", 365, "INR_cr", source_id="report"))          # a segment figure
    for _ in range(30):                                                                     # many standalone mentions
        facts.append(fact("ebitda_cr", "FY2025", 900, "INR_cr", source_id="report2", scope=Scope.standalone))
    s = build_series(facts, "ebitda_cr", {}, today=date(2026, 10, 24))
    assert s.get("FY2026").value == 1500 and s.get("FY2025").value == 1450


def test_periods_not_yet_ended_are_not_actuals():
    from datetime import date
    facts = annual("gross_debt_cr", "INR_cr", {2024: 100, 2025: 110, 2026: 120, 2027: 30})
    s = build_series(facts, "gross_debt_cr", {}, today=date(2026, 10, 24))
    assert "FY2027" not in s.periods and any("not yet ended" in w for w in s.warnings)


def test_quarter_labels_with_spans_and_cut_windows():
    from eia.periods import parse_period
    assert parse_period("Q1 FY 2026-27") == "Q1FY2027"
    assert parse_period("first quarter of FY 2026-27") == "Q1FY2027"
    t = 'Press release titled "results for Q1 FY 27: Net Profit surges to Rs. 17,034 crore".'
    assert [f.period for f in extract_from_sentence(t, ExtractionContext("r", "s"), 1, Scope.unknown)] == ["Q1FY2027"]


def test_slower_cost_growth_is_not_a_risk():
    facts = annual("finance_cost_cr", "INR_cr", {2023: 100, 2024: 130, 2025: 135})
    sig = [s for s in early_warning.run(ctx(facts)).signals if ":finance_cost_cr:" in s.key]
    assert sig and all(s.direction != "risk" for s in sig)


def test_company_segment_target_is_kept_but_national_scale_is_held_out():
    facts = annual("installed_capacity_mw", "MW", {2023: 80000, 2024: 85000, 2025: 89000})
    facts += annual("renewable_capacity_mw", "MW", {2023: 5000, 2024: 9000, 2025: 14600})
    facts += [target("renewable_target_mw", 60000, "MW", 2032), target("capacity_target_mw", 500000, "MW", 2030)]
    res = promise_reality.run(ctx(facts))
    held = " ".join(res.notes)
    assert "500,000" in held and "60,000" not in held


def test_implausible_receivable_days_are_not_used():
    from eia.modules import hidden_risk
    facts = annual("revenue_cr", "INR_cr", {2024: 40000, 2025: 41000})
    facts += annual("receivables_cr", "INR_cr", {2024: 60000, 2025: 110000})   # 547 -> 979 days
    res = hidden_risk.run(ctx(facts), [])
    assert not any(s.key.endswith(":receivables") for s in res.signals)


# ---- dry run 4 ------------------------------------------------------------------------------------------

def test_tiny_finance_cost_moves_are_not_findings():
    facts = annual("finance_cost_cr", "INR_cr", {2023: 100, 2024: 130, 2025: 100})
    facts += annual("revenue_cr", "INR_cr", {2023: 140000, 2024: 150000, 2025: 160000})
    assert not [s for s in early_warning.run(ctx(facts)).signals if ":finance_cost_cr:" in s.key]


def test_accounting_policy_curtailments_and_unit_names_are_not_events():
    c = ExtractionContext("r", "s", "FY2025")
    for t in ["If a plan amendment, curtailment or settlement occurs, the current service cost is remeasured in FY2025.",
              "Sludge is used in the Delayed Coker Unit of the refinery in FY2025.",
              "Borrowing costs are capitalised when a temporary delay is part of the construction process in FY2025."]:
        assert not extract_events(t, c, 1, Scope.unknown), t
    assert extract_events("There was a delay of 22.5 months in the commercial declaration of the mine in FY2025.",
                          c, 1, Scope.unknown)


def test_segment_target_from_a_small_base_is_tracked():
    facts = annual("renewable_capacity_mw", "MW", {2023: 150, 2024: 200, 2025: 290})
    facts.append(target("renewable_target_mw", 10000, "MW", 2030))
    assert not promise_reality.run(ctx(facts)).notes


# ---- dry run 5 ------------------------------------------------------------------------------------------

def test_oil_company_renewable_target_is_not_judged_against_its_small_power_portfolio():
    facts = annual("installed_capacity_mw", "MW", {2023: 190, 2024: 250, 2025: 289})
    facts.append(target("renewable_target_mw", 10000, "MW", 2030))
    assert not promise_reality.run(ctx(facts)).notes


def test_another_x_gw_is_an_increment_not_a_target_level():
    c = ExtractionContext("r", "s", "FY2025")
    t = "We further intend to ramp up our renewable capacity by another 6.5 GW by FY 29-30."
    assert not extract_from_sentence(t, c, 1, Scope.unknown)


# ---- live UI review (an oil marketing company) ----------------------------------------------------------

def test_refiner_renewable_target_from_a_tiny_base_is_tracked():
    facts = annual("renewable_capacity_mw", "MW", {2025: 252})
    facts += annual("installed_capacity_mw", "MW", {2025: 175})
    facts.append(target("renewable_target_mw", 31000, "MW", 2030))
    assert not promise_reality.run(ctx(facts)).notes


def test_national_statistics_and_pipeline_throughput_are_not_company_volumes():
    c = ExtractionContext("r", "s", "FY2025")
    for t in ["India's crude oil production stood at 28.7 MMT in FY2025.",
              "The Corporation's pipeline throughput of 97.6 MMT was achieved in FY2024."]:
        assert not extract_from_sentence(t, c, 1, Scope.unknown), t
    assert extract_from_sentence("Our refineries achieved a crude throughput of 73.3 MMT in FY2024.", c, 1, Scope.unknown)


def test_quarter_change_across_documents_with_unstated_scope_is_not_a_finding():
    from eia.extraction.rules import Scope as S  # noqa: F401
    facts = [fact("pat_cr", "Q1FY2026", 6808, "INR_cr", source_id="tables"),
             fact("pat_cr", "Q1FY2027", 3287, "INR_cr", source_id="filing", scope=Scope.unknown)]
    res = early_warning.run(ctx(facts))
    assert not [s for s in res.signals if ":quarter:pat_cr" in s.key]


# ---- any energy company: business type decides what figures mean -------------------------------------

def test_business_types_from_registry_segments():
    from eia.business import business_type
    assert business_type("power sector finance") == "lender"
    assert business_type("renewable energy finance") == "lender"
    assert business_type("solar module manufacturing") == "manufacturer"
    assert business_type("wind turbine manufacturing") == "manufacturer"
    assert business_type("power exchange") == "exchange"
    assert business_type("lignite mining+generation") == "coal"
    assert business_type("oil refining+marketing") == "oil_gas"
    assert business_type("hydro generation") == "generator"
    assert business_type("conglomerate (energy+other)") == "conglomerate"


def test_manufacturer_gw_figures_are_not_generation_assets():
    from eia.modules import green_growth
    from eia.schema import Company
    facts = annual("installed_capacity_mw", "MW", {2023: 4000, 2024: 9000, 2025: 12000})
    c = ctx(facts)
    c2 = type(c)(c.run_id, Company(name="Example Modules Ltd", nse="EXM", segment="solar module manufacturing"),
                 facts, list(c.sources.values()))
    assert not c2.series("installed_capacity_mw").points
    assert any("Manufacturer" in n for n in green_growth.run(c2).notes)


def test_lender_gets_no_leverage_warning():
    from eia.modules import capital_cash
    from eia.schema import Company
    facts = annual("gross_debt_cr", "INR_cr", {2023: 400000, 2024: 450000, 2025: 500000})
    facts += annual("ebitda_cr", "INR_cr", {2023: 40000, 2024: 45000, 2025: 50000})
    c = ctx(facts)
    c2 = type(c)(c.run_id, Company(name="Example Finance Ltd", nse="EXF", segment="power sector finance"),
                 facts, list(c.sources.values()))
    assert not [s for s in capital_cash.run(c2).signals if "leverage" in s.key]


def test_impossible_utilisation_stops_the_generation_comparison():
    facts = annual("installed_capacity_mw", "MW", {2023: 100, 2024: 120, 2025: 140})
    facts += annual("generation_mu", "MU", {2023: 9000, 2024: 9500, 2025: 9900})     # > 100% PLF
    res = green_growth.run(ctx(facts))
    assert any("not physically" in n for n in res.notes)
    assert not [s for s in res.signals if "generation_mu" in s.key]


# ---- 20-company dry run -------------------------------------------------------------------------------

def test_annual_table_ending_with_an_interim_column_stays_annual():
    from eia.periods import header_periods
    h = "   ".join(f"Mar {y}" for y in range(2015, 2027)) + "   Sep 2026"
    labels = header_periods(h)
    assert labels[0] == "FY2015" and labels[-2] == "FY2026" and labels[-1] == "Q2FY2027"


def test_prose_capacity_that_is_not_the_company_level_is_skipped():
    c = ExtractionContext("r", "s", "FY2025", company_words=("EXCO",))
    for t in ["A record 700 GW of renewable capacity was added, driven primarily by solar PV.",
              "Global renewable capacity increased by 692 GW in the year, led by solar (511 GW) and wind additions (159 GW).",
              "Water intensity (Water consumed (Kl)/ total power generation units (kWh)) 0.0001449 in FY2025",
              "The pumps helped save 101 MWh in FY2025.",
              "Our total locked-in generation capacity 10,800 MW in FY2025.",
              "5,051 MW Renewable Energy Capacity added in FY 2025-26."]:
        assert not extract_from_sentence(t, c, 1, Scope.unknown), t
    assert extract_from_sentence("Our portfolio comprised 14,243 MW of operational renewable energy capacity in FY2025.",
                                 c, 1, Scope.unknown)


def test_generator_capacity_too_small_for_its_revenue_is_held_out():
    from eia.schema import Company
    facts = annual("installed_capacity_mw", "MW", {2025: 12, 2026: 12})
    facts += annual("revenue_cr", "INR_cr", {2025: 11000, 2026: 12500})
    c = ctx(facts)
    c2 = type(c)(c.run_id, Company(name="Example Green Ltd", nse="EXG", segment="renewable generation"),
                 facts, list(c.sources.values()))
    assert not c2.series("installed_capacity_mw").points


def test_physical_jumps_are_not_growth():
    facts = annual("transformation_mva", "MVA", {2025: 1, 2026: 10350})
    s = ctx(facts).series("transformation_mva")
    assert s.periods == ["FY2026"]


def test_small_wobbles_are_not_reversals():
    facts = annual("cfo_cr", "INR_cr", {2023: 1000, 2024: 1030, 2025: 1000, 2026: 1130})   # +3%, -2.9%, +13%
    assert not [s for s in early_warning.run(ctx(facts)).signals if ":cfo_cr:" in s.key]


def test_commissioning_gaps_are_one_finding_per_year():
    from eia.modules import hidden_connections
    from eia.schema import FactType
    facts = annual("installed_capacity_mw", "MW", {2024: 10000, 2025: 10050})
    for i, mw in enumerate([500, 600, 700, 800]):
        facts.append(fact("event", "FY2025", mw, "MW", fact_type=FactType.event, event_category="commissioning",
                          period_end="2024-12-01", passage=f"Commissioned unit {i} of {mw} MW in FY2025."))
    sig = [s for s in hidden_connections.run(ctx(facts)).signals if "event_gap" in s.key]
    assert len(sig) == 1 and "4 commissioning" in sig[0].statement


def test_renewable_above_total_capacity_uses_neither():
    facts = annual("installed_capacity_mw", "MW", {2025: 1800, 2026: 1800})
    facts += annual("renewable_capacity_mw", "MW", {2025: 12500, 2026: 27500})
    c = ctx(facts)
    assert not c.series("installed_capacity_mw").points and not c.series("renewable_capacity_mw").points


def test_singular_borrowing_row_is_debt():
    from eia.extraction.rules import extract_tables
    txt = ("Consolidated Figures in Rs. Crores\nMar 2024   Mar 2025   Mar 2026\n"
           "Borrowing +   8,00,000   8,90,000   9,80,000\n")
    facts = extract_tables(txt, ExtractionContext("r", "s"), 1, Scope.consolidated)
    assert [f.value for f in facts if f.metric == "gross_debt_cr"] == [800000, 890000, 980000]


def test_targets_and_falling_capacity_are_not_commissioning_gaps():
    from eia.modules import hidden_connections
    from eia.schema import FactType
    facts = annual("renewable_capacity_mw", "MW", {2025: 14243, 2026: 15500})
    facts.append(fact("event", "FY2026", 30000, "MW", fact_type=FactType.event, event_category="commissioning",
                      period_end="2026-03-31", passage="We aim to have 30,000 MW commissioned by 2030."))
    facts.append(fact("event", "FY2026", 5000, "MW", fact_type=FactType.event, event_category="commissioning",
                      period_end="2026-03-31", passage="Commissioned 5,000 MW of solar capacity in FY2026."))
    sig = [s for s in hidden_connections.run(ctx(facts)).signals if "event_gap" in s.key]
    assert len(sig) == 1 and "30,000" not in sig[0].statement


# ---- full energy dry run (evening) --------------------------------------------------------------------

def _gen_ctx(facts):
    from eia.schema import Company
    c = ctx(facts)
    return type(c)(c.run_id, Company(name="Example Hydro Ltd", nse="EXH", segment="hydro generation"),
                   facts, list(c.sources.values()))


def test_one_plants_generation_is_not_the_company_level():
    facts = annual("generation_mu", "MU", {2022: 955, 2025: 825, 2026: 332})
    facts += annual("revenue_cr", "INR_cr", {2022: 2417, 2025: 3072, 2026: 4528})   # ~0.3 ₹ cr per MU expected
    assert not _gen_ctx(facts).series("generation_mu").points


def test_ambitious_company_plan_is_tracked_but_national_scale_is_not():
    facts = annual("installed_capacity_mw", "MW", {2024: 1400, 2025: 1460})
    facts += [target("capacity_target_mw", 25000, "MW", 2030), target("capacity_target_mw", 500000, "MW", 2030)]
    res = promise_reality.run(ctx(facts))
    notes = " ".join(res.notes)
    assert "500,000" in notes and "25,000" not in notes


def test_far_smaller_values_are_not_a_target_revision():
    facts = [target("capacity_target_mw", 45, "MW", 2030), target("capacity_target_mw", 30000, "MW", 2030)]
    assert not [s for s in promise_reality.run(ctx(facts)).signals if ":revision:" in s.key]
