"""Key-free exchange sources: parsing of NSE API payloads and agent ingestion, with fakes (no network)."""
from datetime import date

import pytest

from eia.agent import ResearchAgent
from eia.config import get_settings
from eia.db import Store
from eia.providers.direct import DirectFindings, announcement_digest, parse_annual_reports, parse_announcements
from eia.providers.fetch import FetchResult
from eia.providers.llm import NullLLM
from eia.providers.search import NullSearch, SearchResult
from eia.schema import Company, SourceTier

AR_API = {"data": [
    {"companyName": "Kestrel Hydro Power Limited", "fromYr": "2023", "toYr": "2024",
     "fileName": "https://nsearchives.nseindia.com/annual_reports/AR_1_KESTREL_2023_2024.pdf"},
    {"companyName": "Kestrel Hydro Power Limited", "fromYr": "2024", "toYr": "2025",
     "fileName": "https://nsearchives.nseindia.com/annual_reports/AR_2_KESTREL_2024_2025.zip"},
    {"companyName": "Kestrel Hydro Power Limited", "fromYr": "2019", "toYr": "2020",
     "fileName": "https://nsearchives.nseindia.com/annual_reports/AR_0_KESTREL_2019_2020.pdf"}]}
ANN_API = [
    {"desc": "Outcome of Board Meeting", "an_dt": "12-Aug-2026 18:07:19",
     "attchmntFile": "https://nsearchives.nseindia.com/corporate/KESTREL_12082026_results.pdf",
     "attchmntText": "Approved unaudited financial results for the quarter ended June 30, 2026"},
    {"desc": "Change in Directors", "an_dt": "01-Aug-2026 10:00:00",
     "attchmntFile": "https://nsearchives.nseindia.com/corporate/KESTREL_dir.pdf", "attchmntText": "Appointment"},
    {"desc": "Commissioning of project", "an_dt": "20-Jul-2026 09:00:00",
     "attchmntFile": "https://nsearchives.nseindia.com/corporate/KESTREL_cod.pdf",
     "attchmntText": "The company commissioned 120 MW of hydro capacity in Himachal Pradesh"}]


def test_parse_annual_reports_latest_first():
    r = parse_annual_reports(AR_API, "KESTREL")
    assert [x.url.rsplit("_", 2)[-1] for x in r] == ["2025.zip", "2024.pdf"]
    assert "annual report 2024-2025" in r[0].title


def test_parse_announcements_keeps_relevant_and_builds_dated_digest():
    docs, heads = parse_announcements(ANN_API, "KESTREL")
    assert {d.url.rsplit("/", 1)[-1] for d in docs} == {"KESTREL_12082026_results.pdf", "KESTREL_cod.pdf"}
    assert docs[0].date == "2026-08-12" and len(heads) == 3
    text = announcement_digest("KESTREL", heads)
    assert "On 20 July 2026, Commissioning of project: The company commissioned 120 MW" in text


class FakeDirect:
    def discover(self, symbol):
        docs, heads = parse_announcements(ANN_API, symbol)
        return DirectFindings(results=docs + [SearchResult("Screener", "https://www.screener.in/company/KESTREL/consolidated/")],
                              digest=("KESTREL NSE corporate announcements", "https://www.nseindia.com/get-quotes/equity?symbol=KESTREL",
                                      announcement_digest(symbol, heads)), errors=["NSE annual reports: HTTP 403"])


SCREENER = b"""<html><body><p>Consolidated Figures in Rs. Crores</p><table>
<tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th></tr>
<tr><td>Sales +</td><td>900</td><td>1,010</td><td>1,060</td></tr>
<tr><td>Operating Profit</td><td>600</td><td>650</td><td>655</td></tr></table></body></html>"""


class FakeFetcher:
    def fetch(self, url):
        if "screener" in url:
            return FetchResult(url, True, SCREENER, "text/html", url)
        return FetchResult(url, False, error="HTTP 404")


def test_live_run_without_any_api_key_reads_exchange_sources():
    st = Store(":memory:")
    co = Company(name="Kestrel Hydro Power Ltd", nse="KESTREL")
    out = ResearchAgent(st, get_settings(), search=NullSearch(), llm=NullLLM(), fetcher=FakeFetcher(),
                        direct=FakeDirect(), today=date(2026, 9, 1)).research(co, max_rounds=1)
    srcs = st.sources(out.run_id)
    ok = [s for s in srcs if s.fetch_status == "ok"]
    assert {s.domain for s in ok} == {"nseindia.com", "screener.in"}
    assert any(s.tier == SourceTier.exchange for s in ok) and any(s.tier == SourceTier.media for s in ok)
    facts = st.facts(out.run_id)
    assert any(f.metric == "revenue_cr" and f.period == "FY2025" and f.value == 1060 for f in facts)
    ev = [f for f in facts if f.event_category == "commissioning"]
    assert ev and ev[0].period_end == "2026-07-20" and ev[0].value == 120
    msgs = " ".join(e.message for e in st.events(out.run_id))
    assert "NSE annual reports: HTTP 403" in msgs  # failures are logged, research continues


def test_zip_annual_report_is_unpacked():
    import io
    import zipfile
    canvas = pytest.importorskip("reportlab.pdfgen.canvas", reason="reportlab not installed")
    from eia.extraction.documents import parse_bytes
    pdf = io.BytesIO()
    c = canvas.Canvas(pdf)
    c.drawString(72, 800, "Installed capacity stood at 1,200 MW as on 31 March 2025.")
    c.save()
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("AR_2025.pdf", pdf.getvalue())
    doc = parse_bytes(z.getvalue(), "application/zip")
    assert doc.kind == "pdf" and "1,200 MW" in doc.full_text
