"""DEMO MODE — synthetic data only.

A fictitious company ("Aurora Grid Renewables Ltd") with synthetic disclosures. The documents are plain text and
go through exactly the same pipeline as live research (search -> fetch -> parse -> extract -> modules ->
hypotheses -> counter-evidence), using an in-memory search index and fetcher instead of the internet.
Nothing here describes a real company, and none of it is used by live research.
"""
from __future__ import annotations

from typing import Optional

from .providers.fetch import FetchResult
from .providers.search import SearchResult, StaticSearch
from .schema import Company

BANNER = "SYNTHETIC DEMO DOCUMENT — fictitious company, invented figures. Not real data.\n"

DEMO_COMPANY = Company(
    name="Aurora Grid Renewables Ltd", nse="AURORA-DEMO", aliases=["Aurora Grid"],
    segment="renewable generation (synthetic)", website="aurora-demo.invalid", eligible=True,
    resolution_note="SYNTHETIC demo company — not a listed entity.")

AR_FY2024 = BANNER + """Aurora Grid Renewables Ltd
Annual Report 2023-24

Chairman's message
Operational renewable capacity stood at 3,450 MW as on 31 March 2024.
On 14 September 2023, the 50:50 joint venture of the company commissioned 1,200 MW of wind-solar hybrid capacity in Tamil Nadu.
\f""" + BANNER + """Consolidated financial highlights (₹ in crore)
Particulars   FY2021   FY2022   FY2023   FY2024
Revenue from operations   2,610   3,050   3,640   4,310
EBITDA   2,190   2,560   3,020   3,560
Profit after tax   540   610   690   720
Finance costs   880   1,020   1,240   1,610
Net cash from operating activities   1,930   2,200   2,350   2,480
Capital expenditure   2,700   3,900   5,600   7,200
Total borrowings   12,400   15,800   20,100   26,400
Cash and cash equivalents   1,210   1,450   1,620   2,050
Trade receivables   650   760   980   1,390
Total equity   6,300   6,900   7,800   8,500
\f""" + BANNER + """Operating highlights
Particulars   FY2021   FY2022   FY2023   FY2024
Operational renewable capacity (MW)   1,700   2,050   2,700   3,450
Generation (MU)   3,560   4,150   4,700   5,250
Average CUF (%)   24.0   24.1   23.9   23.4
Solar capacity (MW)   950   1,200   1,600   2,050
Wind capacity (MW)   600   700   900   1,150
Hydro capacity (MW)   150   150   200   250
Emission intensity (tCO2/MWh)   0.021   0.019   0.017   0.016
"""

AR_FY2025 = BANNER + """Aurora Grid Renewables Ltd
Annual Report 2024-25

Operational renewable capacity stood at 4,300 MW as on 31 March 2025.
On 12 February 2025, the company commissioned 450 MW of solar capacity at Site-K in Rajasthan.
On 5 March 2025, the company raised ₹ 2,500 crore through green bonds to part-fund its build-out.
\f""" + BANNER + """Consolidated financial highlights (₹ in crore)
Particulars   FY2024   FY2025
Revenue from operations   4,310   5,120
EBITDA   3,560   4,050
Profit after tax   720   640
Finance costs   1,610   2,050
Net cash from operating activities   2,480   2,510
Capital expenditure   7,200   8,900
Total borrowings   26,400   33,800
Cash and cash equivalents   2,050   2,300
Trade receivables   1,390   2,060
Total equity   8,500   9,200
\f""" + BANNER + """Operating highlights
Particulars   FY2024   FY2025
Operational renewable capacity (MW)   3,450   4,300
Generation (MU)   5,250   5,720
Average CUF (%)   23.4   22.6
Solar capacity (MW)   2,050   2,650
Wind capacity (MW)   1,150   1,350
Hydro capacity (MW)   250   300
Emission intensity (tCO2/MWh)   0.016   0.014
"""

INVESTOR_PRES = BANNER + """Aurora Grid Renewables Ltd — Investor Presentation Q4 FY2025

Strategy 2030
The company targets an operational renewable capacity of 10,000 MW by FY2030.
The company plans a capex of ₹ 60,000 crore by FY2030 to deliver this growth.
On 18 April 2025, the company was awarded a 500 MW wind-solar hybrid project in Karnataka.
"""

Q1_RESULTS = BANNER + """Aurora Grid Renewables Ltd — Quarterly results press release for the quarter ended 30 June 2025

Consolidated results (₹ in crore)
Particulars   Q1FY2025   Q1FY2026
Revenue from operations   1,410   1,450
EBITDA   1,160   1,150
Generation (MU)   1,720   1,540

Trade receivables as on 30 June 2025 stood at ₹ 2,240 crore.
"""

RATING = BANNER + """Demo Ratings — Rating rationale: Aurora Grid Renewables Ltd (credit rating)

Date: 20 May 2025
The long-term rating outlook revised to Negative from Stable on 20 May 2025, reflecting rising leverage.
"""

NEWS = BANNER + """Demo Business Daily — Aurora Grid Renewables update
Published: 2 June 2025

Aurora Grid Renewables reported revenue from operations of ₹ 5,410 crore in FY2025, according to a media summary.
The 600 MW Site-R project in Gujarat has been delayed to Q3 FY2026 because of transmission constraints.
"""

PIPELINE = BANNER + """Aurora Grid Renewables Ltd — Project pipeline update (investor presentation annexure)

As on 31 March 2025, capacity under construction stood at 3,100 MW, with commercial dates scheduled between FY2026 and FY2028.
"""

DOCS: dict[str, tuple[str, str]] = {   # url -> (title, text)
    "synthetic://aurora-demo.invalid/annual-report-2023-24.txt": ("Aurora Grid Renewables Annual Report 2023-24", AR_FY2024),
    "synthetic://aurora-demo.invalid/annual-report-2024-25.txt": ("Aurora Grid Renewables Annual Report 2024-25", AR_FY2025),
    "synthetic://aurora-demo.invalid/investor-presentation-q4fy2025.txt":
        ("Aurora Grid Renewables Investor Presentation Q4 FY2025", INVESTOR_PRES),
    "synthetic://aurora-demo.invalid/q1fy2026-results.txt":
        ("Aurora Grid Renewables quarterly results Q1 FY2026", Q1_RESULTS),
    "synthetic://demo-ratings.invalid/aurora-rationale.txt": ("Demo Ratings: Aurora Grid credit rating rationale", RATING),
    "synthetic://demo-news.invalid/aurora-delay.txt": ("Demo Business Daily: Aurora Grid Renewables project delay", NEWS),
    "synthetic://aurora-demo.invalid/pipeline-annexure.txt":
        ("Aurora Grid Renewables capacity under construction pipeline", PIPELINE),
}


def _r(url: str) -> SearchResult:
    return SearchResult(DOCS[url][0], url, "synthetic demo document")


def demo_search() -> StaticSearch:
    """Query substring -> results. The pipeline document is only reachable through a counter-evidence query."""
    u = list(DOCS)
    return StaticSearch({
        "annual report": [_r(u[1]), _r(u[0])],
        "quarterly results": [_r(u[3])],
        "investor presentation": [_r(u[2])],
        "credit rating": [_r(u[4])],
        "delay": [_r(u[5])],
        "capacity under construction": [_r(u[6])],
    })


class SyntheticFetcher:
    def fetch(self, url: str) -> FetchResult:
        if url in DOCS:
            return FetchResult(url, True, DOCS[url][1].encode("utf-8"), "text/plain", url)
        return FetchResult(url, False, error="not in synthetic corpus")


def run_demo(store, settings=None, progress=None, max_rounds: Optional[int] = None):
    """Run the full pipeline on the synthetic company. Returns RunOutcome."""
    from .agent import ResearchAgent
    from .config import get_settings
    from .providers.llm import NullLLM
    from datetime import date
    s = settings or get_settings()
    agent = ResearchAgent(store, s, search=demo_search(), llm=NullLLM(), fetcher=SyntheticFetcher(),
                          progress=progress, today=date(2025, 8, 15))
    return agent.research(DEMO_COMPANY, mode="demo", max_rounds=max_rounds or 3)
