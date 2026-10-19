# Unseen-company validation — honest record

**Run on:** 17 Oct 2026 · **Code:** `eia/` · **Re-run with:** `scripts/validate_real_docs.sh OUTDIR`
plus the NHPC command at the bottom.

## Why the test used transcribed documents

The build sandbox blocks outbound traffic to search APIs, NSE, BSE and company websites, so the app's own
discovery and fetching could not reach the internet there. Live mode was tried anyway: every search was refused
by the network, each failure was logged, and the run ended as `partial` with no invented data.

To test generalisation on real disclosures instead, I retrieved public documents with a separate web-reading
tool. I saved its output to the `.txt` files in this folder and ingested them through the app's normal
document-upload path, keeping each original URL so source tiers are classified correctly.

These are transcriptions, not the raw files. Tables were copied verbatim on request. Where the tool condensed
labels or dropped details, the files keep exactly what was returned and nothing was edited. One example: the KPI
Green capacity lines have condensed labels; another: the NHPC filing headers lost their dates.

One fetched NSE PDF was excluded: a "newspaper publication" whose figures belonged to a different company.

## Results

| # | Company (NSE) | Code state | Result |
|---|---|---|---|
| 1 | **KPI Green Energy** (KPIGREEN) | unchanged baseline | **FAILED** — 0 facts from 4 documents; all six modules "insufficient data". Causes: content-type taken from URL (`.pdf` text sent to the PDF parser), `3 months ended 31-03-2026` / `Mar 2025` headers, `Lakhs (INR)` / `Figures in Rs. Crores` unit notes, single-period balance-sheet sections, labels `Sales` / `Interest` / `cash flow from/used in`, `950+ MW`. |
| 1b | KPI Green (after generic fixes) | fixed | 94 facts; FY26 lakhs→crore conversions checked by hand; three real cross-source conflicts surfaced (FY26 borrowings ₹4,532 cr exchange vs ₹5,197 cr aggregator; CFO; EBITDA definitions). One more flaw found and fixed: growth computed from a negative base (CFO −₹57 cr → +522.8%). |
| 2 | **Torrent Power** (TORNTPOWER) | frozen after #1b | **PARTIAL, with one materially wrong finding**: “Thin interest coverage: 0.00x — Supported/strong”. Cause: the unlabelled ratio row `Net Debt / EBITDA 2.24 …` was read as EBITDA in ₹ crore under a page note “Rs in Crore”. Also missed: all aggregator rows (12 `Mar YYYY` columns counted as words), the `year-end` balance sheet, `EBIDTA`/`PBDIT`, `Q1 26-27`, `21-22` headers. Correct: revenue matched across filing (₹28,966.31 cr) and presentation (₹28,966 cr) without a false conflict; capex, CFO, finance costs, net worth. |
| 2b | Torrent Power (after generic fixes) | fixed | 168 facts; wrong finding gone; Contradiction Lab shows EBITDA definitional gaps (aggregator “Operating Profit” vs company PBDIT, 5–8%). |
| 3 | **NHPC** (NHPC) | **frozen** (sha256 of `eia/*.py` = `e75d7773…`, unchanged before/after) | **PASSED, with limited depth.** 124/124 aggregator facts correct. The filing whose column dates were lost produced 0 facts — correct refusal to guess periods. Eight findings, none marked Supported, because the only dated evidence was aggregator-tier. Arithmetic checked: debt/EBITDA 52,327 / 4,097 = 12.8x; EBITDA margin 53.2% → 35.3%. Promise vs Reality was insufficient: no capacity or target data in the documents. |

**Independent audit:** every aggregator-derived fact for all three companies (48 + 124 + 124 = 296) was
compared with a separate, simple parser of the same files: 296 matched, 0 mismatched, 0 unexpected.

## What the fixes were (all generic, none company-specific)

- Content type detected from file bytes, not URL.
- Table-header periods: `n months ended dd-mm-yyyy`, `Quarter ended 30 June 2025`, `Mar 2025`, `Jun-25`,
  `Q1 26-27`, `FY 25-26`, `21-22`, and bare dates with quarter/year cues. Ambiguous columns stay unlabelled.
- Growth/% columns kept as placeholders so values stay aligned.
- An unreadable header stops rows being attributed to the previous header.
- Unit notes: `Figures in Rs. Crores`, `Reporting unit: Lakhs (INR)`, `Rs in Crore`.
- An explicit row unit (`(times)`, `(₹)`) overrides the page unit.
- Ratio, per-share, coverage and margin labels are never read as amounts.
- Labels: `Sales`, `Interest`, `EBIDTA`, `PBDIT`, `capacity energised`, `Borrowings, non-current`, and
  variants of cash flow from/used in operations.
- Gross debt is computed as non-current + current borrowings, a documented sum whose two inputs are both kept
  in the passage.
- `950+ MW` style numbers; `;`-separated clauses; table rows skipped by the sentence extractor.
- `[[page N]]` markers in text transcripts keep printed page numbers.
- Growth from a zero or negative base is reported as not meaningful.

Each fix has a unit test on invented data (`tests/test_extraction.py`, `tests/test_calculations.py`). The three
companies are now offline regression fixtures (`tests/test_real_documents.py`), so they no longer count as unseen.

## Not validated here

- The live search → fetch → PDF path against real websites, because of the network block.
- PyMuPDF itself, which isn't installable in the sandbox; the pdfplumber fallback was exercised with a
  generated PDF.
- The optional LLM extraction against a real model; it was only tested with a stub.

To validate those, run with a search key on an unrestricted machine.

```
python scripts/research.py NHPC --no-search --db OUT/nhpc.sqlite --out OUT/nhpc \
  --doc validation/nhpc/results_fy2026_consolidated_nse.txt=https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_158237_15052026224723_iXBRL_WEB.html \
  --doc validation/nhpc/screener_consolidated.txt=https://www.screener.in/company/NHPC/consolidated/
```
