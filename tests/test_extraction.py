import io

import pytest

from eia.extraction.documents import parse_bytes, parse_text
from eia.extraction.rules import ExtractionContext, extract_document
from eia.schema import FactStatus, FactType


def run(text, title=""):
    return extract_document(parse_text(text, title), ExtractionContext("r", "s1"))


def by(facts, metric, period=None):
    return [f for f in facts if f.metric == metric and (period is None or f.period == period)]


def test_sentence_with_unit_and_period():
    fs = run("Installed capacity stood at 12.5 GW as on 31 March 2025.")
    f = by(fs, "installed_capacity_mw")[0]
    assert f.value == 12500 and f.unit == "MW" and f.period == "FY2025"
    assert f.status == FactStatus.source_verified and "12.5" in f.passage


def test_target_extraction():
    fs = run("The company aims to reach renewable capacity of 20 GW by FY2030.\nAnnual report 2024-25")
    t = [f for f in fs if f.fact_type == FactType.target][0]
    assert t.metric == "renewable_target_mw" and t.value == 20000 and t.target_year == 2030


def test_table_with_page_unit():
    text = ("Consolidated statement (₹ in crore)\nParticulars   FY2024   FY2025\n"
            "Revenue from operations   10,250.5   11,300.0\nFinance costs   1,100   1,450\n")
    fs = run(text)
    rev = {f.period: f.value for f in by(fs, "revenue_cr")}
    assert rev == {"FY2024": 10250.5, "FY2025": 11300.0}
    assert all(f.scope.value == "consolidated" for f in by(fs, "revenue_cr"))


def test_table_without_unit_is_skipped():
    text = "Particulars   FY2024   FY2025\nRevenue from operations   10,250   11,300\n"
    assert not by(run(text), "revenue_cr")


def test_lakh_conversion_in_table():
    text = "(₹ in lakhs)\nParticulars   FY2024   FY2025\nTotal borrowings   50,000   60,000\n"
    fs = by(run(text), "gross_debt_cr")
    assert {f.value for f in fs} == {500.0, 600.0}


def test_change_amount_not_taken_as_level():
    fs = run("Revenue from operations increased by ₹ 500 crore in FY2025.")
    assert not by(fs, "revenue_cr")


def test_asof_wins_over_future_window_for_stock_metric():
    fs = run("As on 31 March 2025, capacity under construction stood at 3,100 MW, with commissioning scheduled "
             "between FY2026 and FY2028.")
    f = by(fs, "capacity_under_construction_mw")[0]
    assert f.period == "FY2025"


def test_event_extraction_with_date():
    fs = run("On 12 February 2025, the company commissioned 300 MW of solar capacity in Rajasthan.")
    e = [f for f in fs if f.fact_type == FactType.event][0]
    assert e.event_category == "commissioning" and e.value == 300 and e.period_end == "2025-02-12"


def test_html_table_rows():
    html = b"""<html><head><title>Results</title></head><body><p>(Rs. in crore)</p><table>
    <tr><th>Particulars</th><th>Q1FY2025</th><th>Q1FY2026</th></tr>
    <tr><td>Revenue from operations</td><td>2,100</td><td>2,350</td></tr></table></body></html>"""
    doc = parse_bytes(html, "text/html")
    fs = extract_document(doc, ExtractionContext("r", "s1"))
    assert {f.period: f.value for f in by(fs, "revenue_cr")} == {"Q1FY2025": 2100, "Q1FY2026": 2350}


def test_pdf_page_numbers_are_kept():
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    canvas = pytest.importorskip("reportlab.pdfgen.canvas", reason="reportlab not installed")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, "Annual Report 2024-25")
    c.showPage()
    c.drawString(72, 800, "Operational renewable capacity stood at 2,450 MW as on 31 March 2025.")
    c.showPage()
    c.save()
    doc = parse_bytes(buf.getvalue(), "application/pdf")
    assert len(doc.pages) == 2
    fs = extract_document(doc, ExtractionContext("r", "s1"))
    f = by(fs, "renewable_capacity_mw")[0]
    assert f.page == 2 and f.value == 2450


# ---- formats found during the unseen-company test (fictitious values) ----------------------------

def test_numeric_ended_headers_and_lakh_unit_note():
    text = ("Basis: Consolidated\nReporting unit: Lakhs (INR)\n"
            "Particulars   3 months ended 31-03-2026   Year ended 31-03-2026\n"
            "Revenue from operations   12,345.60   45,678.90\nFinance costs   1,000.00   4,000.00\n")
    fs = run(text)
    rev = {f.period: round(f.value, 4) for f in by(fs, "revenue_cr")}
    assert rev == {"Q4FY2026": 123.456, "FY2026": 456.789}
    assert all(f.scope.value == "consolidated" for f in fs)


def test_month_year_headers_and_aggregator_labels():
    text = ("Figures in Rs. Crores\nMar 2023   Mar 2024   Mar 2025\nSales +   100   150   210\n"
            "Interest   5   8   12\nBorrowings +   40   60   90\nCash from Operating Activity +   -7   20   31\n")
    fs = run(text)
    assert {f.period: f.value for f in by(fs, "revenue_cr")} == {"FY2023": 100, "FY2024": 150, "FY2025": 210}
    assert {f.period: f.value for f in by(fs, "finance_cost_cr")}["FY2025"] == 12
    assert {f.period: f.value for f in by(fs, "cfo_cr")}["FY2023"] == -7


def test_quarterly_month_headers():
    text = "(₹ in crore)\nJun 2025   Sep 2025   Dec 2025\nRevenue from operations   10   11   12\n"
    assert {f.period for f in by(run(text), "revenue_cr")} == {"Q1FY2026", "Q2FY2026", "Q3FY2026"}


def test_ambiguous_bare_date_columns_are_skipped_not_guessed():
    text = ("(₹ in crore)\nQuarter ended   Year ended\n31.03.2026   31.12.2025   31.03.2025   31.03.2026\n"
            "Revenue from operations   10   11   9   40\n")
    fs = by(run(text), "revenue_cr")
    assert {f.period for f in fs} == {"Q3FY2026"}  # only the unambiguous column


def test_single_period_balance_sheet_section_and_borrowing_sum():
    text = ("Reporting unit: Lakhs (INR)\nStatement of assets and liabilities (year ended 31-03-2026)\n"
            "Trade receivables   1,000.00\nNon-current borrowings   20,000.00\nCurrent borrowings   5,000.00\n")
    fs = run(text)
    assert by(fs, "receivables_cr")[0].value == 10 and by(fs, "receivables_cr")[0].period == "FY2026"
    gd = by(fs, "gross_debt_cr")[0]
    assert gd.value == 250 and gd.extraction_method == "table_sum" and gd.status == FactStatus.source_verified


def test_ratio_rows_never_take_the_page_money_unit():
    text = ("(In ₹ Crore)\nMetric   FY25   FY24\nTotal Revenue (₹ Crore)   500   400\n"
            "Debt To Equity (times)   0.5   0.9\nEPS (₹)   4.2   3.1\nTotal Outside Liability To Total Net Worth (times)   1.1   1.4\n")
    fs = run(text)
    assert {f.period: f.value for f in by(fs, "revenue_cr")} == {"FY2025": 500, "FY2024": 400}
    assert not by(fs, "gross_debt_cr") and not by(fs, "equity_cr")


def test_plus_suffixed_numbers_and_semicolon_clauses():
    fs = run("Cumulative capacity energised till FY25: 950+ MW; group capacity target by 2030: 10+ GW")
    cap = by(fs, "installed_capacity_mw")
    assert cap and cap[0].value == 950 and cap[0].fact_type == FactType.reported and cap[0].period == "FY2025"


def test_text_with_pdf_url_is_parsed_as_text_and_page_markers_kept():
    data = "[[page 36]]\nInstalled capacity stood at 1,200 MW as on 31 March 2025.".encode()
    doc = parse_bytes(data, "text/plain", "https://example.org/report.pdf")
    assert doc.kind == "text" and doc.pages[0].number == 36


def test_unlabelled_ratio_rows_are_not_amounts():
    text = ("Rs in Crore\nParticulars   21-22   22-23   23-24\nNet Debt / EBITDA   2.24   1.97   2.25\n"
            "Net Debt Equity Ratio   0.80   0.82   0.80\nEBIDTA (₹ Crore)   3,826   5,141   4,903\n")
    fs = run(text)
    assert not by(fs, "net_debt_cr")
    assert {f.period: f.value for f in by(fs, "ebitda_cr")} == {"FY2022": 3826, "FY2023": 5141, "FY2024": 4903}


def test_many_month_columns_and_year_end_balance_sheet():
    hdr = "   ".join(f"Mar {y}" for y in range(2015, 2027))
    vals = "   ".join(str(100 + i) for i in range(12))
    fs = run(f"Figures in Rs. Crores\n{hdr}\nBorrowings +   {vals}\n")
    assert len(by(fs, "gross_debt_cr")) == 12
    bs = ("Reporting unit: Lakhs (INR)\nStatement of Assets and Liabilities (year-end 31-03-2026 only)\n"
          "Borrowings, non-current   1,000.00\nBorrowings, current   500.00\n")
    gd = by(run(bs), "gross_debt_cr")
    assert gd and gd[0].value == 15 and gd[0].period == "FY2026"


def test_short_span_quarter_headers_with_growth_column():
    text = "Rs in Crore\nParticulars   Q1 26-27   Q1 25-26   % Growth   FY 25-26\nRevenue from Operations   8,1   7,9   3%   28,9\n"
    text = text.replace("8,1", "8,124").replace("7,9", "7,906").replace("28,9", "28,966")
    got = {f.period: f.value for f in by(run(text), "revenue_cr")}
    assert got == {"Q1FY2027": 8124, "Q1FY2026": 7906, "FY2026": 28966}


def test_unreadable_header_stops_row_attribution():
    text = ("(₹ in crore)\nParticulars   FY2024   FY2025\nRevenue from operations   10   12\n"
            "Particulars   H1 A   H1 B   Q9 X   2023 2024 ??\nRevenue from operations   1   2   3   4\n")
    vals = {f.value for f in by(run(text), "revenue_cr")}
    assert vals == {10, 12}


# ---- oil, gas, coal and transmission businesses (fictitious values) ------------------------------

def test_coal_production_and_target():
    fs = run("Raw coal production stood at 781.1 million tonnes in FY2025.\n"
             "The company targets coal production of 1 billion tonnes by FY2030.")
    p = by(fs, "coal_production_mt")
    assert p and p[0].value == 781.1 and p[0].unit == "Mt" and p[0].period == "FY2025"
    t = by(fs, "coal_target_mt")
    assert t and t[0].value == 1000 and t[0].target_year == 2030


def test_oil_gas_units():
    fs = run("In FY2025, oil and gas production was 42.5 MMTOE. Crude oil production of 19.2 MMT and "
             "natural gas production of 20.1 BCM were reported in FY2025. Refinery throughput was 68.3 MMT in FY2025.")
    assert by(fs, "oil_gas_production_mtoe")[0].value == 42.5
    assert by(fs, "crude_production_mt")[0].value == 19.2
    assert by(fs, "gas_production_bcm")[0].value == 20.1
    assert by(fs, "refinery_throughput_mt")[0].value == 68.3


def test_transmission_network():
    fs = run("As on 31 March 2025 the transmission network comprised 1,80,000 ckm and transformation capacity "
             "of 5,50,000 MVA.")
    assert by(fs, "transmission_ckm")[0].value == 180000
    assert by(fs, "transformation_mva")[0].value == 550000


def test_mass_units_never_attach_to_money_or_power():
    fs = run("Revenue from operations was 1,200 MT in FY2025. Installed capacity was 5 MT in FY2025.")
    assert not by(fs, "revenue_cr") and not by(fs, "installed_capacity_mw")


def test_total_and_renewable_targets_in_one_sentence_are_kept_apart():
    fs = run("The company targets a total installed capacity of 149 GW by 2032, including 60 GW of renewable "
             "energy capacity.")
    assert [(f.metric, f.value) for f in by(fs, "capacity_target_mw")] == [("capacity_target_mw", 149000)]
    assert [(f.metric, f.value) for f in by(fs, "renewable_target_mw")] == [("renewable_target_mw", 60000)]


class _FakePage:
    def __init__(self, text):
        self.text = text

    def get_text(self, kind="text"):
        return self.text


class _FakePdf(list):
    pass


def test_long_reports_keep_financial_statements_beyond_the_page_budget():
    from eia.extraction.documents import choose_pages
    pages = [_FakePage(f"Page {i}: corporate governance and CSR narrative.") for i in range(700)]
    pages[519] = _FakePage("Consolidated Statement of Profit and Loss for the year ended 31 March 2025")
    pages[609] = _FakePage("Ten Year Financial Highlights: revenue from operations, borrowings, capex")
    pages[450] = _FakePage("Installed capacity stood at 1,200 MW; generation 5,000 MU; PLF 78%")
    chosen = choose_pages(_FakePdf(pages), 350)
    assert len(chosen) == 350 and chosen == sorted(chosen)
    assert {519, 609, 450} <= set(chosen) and set(range(100)) <= set(chosen)


def test_short_reports_are_read_whole():
    from eia.extraction.documents import choose_pages
    assert choose_pages(_FakePdf([_FakePage("x")] * 40), 350) == list(range(40))
