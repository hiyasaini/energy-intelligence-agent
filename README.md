# Energy Intelligence Agent

**ATMOS 2026 · Track B: Energy, Power & Renewables**

An autonomous research agent for listed Indian energy companies. It resolves the company you enter, discovers
its disclosures, extracts traceable facts, runs six analytical modules, generates hypotheses, searches for
evidence against them, and exports an auditable report. No company is hard-coded: the same generic schema,
extraction rules and modules run on whatever company is entered.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py            # opens the dashboard
```

You can also run it from the command line:

```bash
python scripts/research.py --demo --out reports/
python scripts/research.py "Tata Power" --out reports/                 # live (needs a search provider)
python scripts/research.py KPIGREEN --no-search --doc annual_report.pdf=https://original/url.pdf
python -m pytest                                                       # 102 tests, no network needed
```

### API keys (`.env`)

| Purpose | Variable | Required? |
|---|---|---|
| Key-free primary sources (default on) | `EIA_DIRECT_SOURCES=on`: NSE annual reports, NSE corporate filings and Screener tables for the company's NSE symbol | No key needed |
| Live source discovery | `EIA_SEARCH_PROVIDER` = `tavily` · `serper` · `brave` · `anthropic` · `duckduckgo` · `none`, plus the matching `TAVILY_API_KEY` / `SERPER_API_KEY` / `BRAVE_API_KEY` / `ANTHROPIC_API_KEY` | For live discovery. `duckduckgo` needs no key but is fragile. With `none`, the app analyses uploaded documents and pasted URLs only. |
| Optional LLM (query planning, grounded extraction, labelled interpretation) | `EIA_LLM_PROVIDER` = `anthropic` · `openai` · `none`, plus `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (any OpenAI-compatible endpoint via `OPENAI_BASE_URL`) | No |
| Bounds | `EIA_MAX_ROUNDS` (default 3), `EIA_MAX_SOURCES_PER_ROUND`, `EIA_MAX_PDF_PAGES` | No |

## Demo video

## Demo video

▶ **[Watch the 2-minute demo](https://drive.google.com/file/d/1C6c_MIlGpouNDyKll6QXEwHwck4_eI-b/view?usp=sharing)**: the agent running live on NTPC (NIFTY 50, Track B).

The recording was made with `scripts/make_demo_video.py`, which drives the real app in a headless browser,
walks through every page and writes `demo_video.mp4` (no voice, so a voiceover can be added), with a
timed voiceover script in `demo_voiceover_script.txt`. To make it again:

    pip install -r requirements-video.txt
    python -m playwright install chromium
    python scripts/make_demo_video.py --company NTPC

```bash
pip install -r requirements-video.txt
python -m playwright install chromium
python scripts/make_demo_video.py --company NTPC
```

## Modes

- **Live research** discovers sources at runtime with the configured search provider. You can also upload
  PDF/HTML/TXT disclosures or paste URLs; these go through the same pipeline.
- **Demo (synthetic data)** uses a fictitious company, *Aurora Grid Renewables Ltd*, with synthetic documents
  run through the identical pipeline via an in-memory search index. Every demo page and report carries a
  `DEMO MODE — SYNTHETIC DATA` banner. Demo data lives only in `eia/demo.py` and is never used by live research.

## Dashboard

The **Overview** page is the home screen. Its Dashboard tab shows a header strip (company, market price, 52-week
range, NIFTY 50), financial performance (revenue, EBITDA, PAT), operational metrics (capacity by source, capacity under
construction, generation), NIFTY 50 benchmarking with 1M–5Y ranges, balance-sheet ratios computed from filings, the
agent's verdict, a project map (Indian states named in project disclosures), renewable share, emission intensity,
upcoming projects and recent headlines. The Research summary tab keeps the earlier view: search bar, company header with share price (Yahoo Finance, optional),
revenue, capacity and a rule-based risk-signal level, then research progress, sources analysed, key highlights,
evidence confidence, overall outlook, financial and operational trends, energy mix, emissions intensity, top
findings, a mini discovery graph and the recent timeline. Every figure comes from the run's extracted facts and
findings; a panel whose data was not found says so instead of showing a number. Market data is display-only and
can be switched off with `EIA_MARKET_DATA=none`.

Every link works: panel links and highlight tiles jump to the right page (with filters) and keep the selected run;
web sources open in a new tab (PDFs at the cited page); every piece of evidence has a *View page in document*
button that opens the built-in reader with the passage highlighted.

## Dashboard pages

| Page | What it shows |
|---|---|
| Overview | Company header and KPI tiles; executive view, key metrics, latest developments and insights tabs |
| Promise vs Reality … Early Warning | One page per analytical module: charts, table, findings, calculations, missing data |
| Signal Radar | Company input with safe identity resolution (ambiguous names require an explicit choice), research settings, document upload, live progress, discovery summary, module status, research log |
| Discovery Feed | Ranked findings (severity × evidence strength × verification status), filterable; each opens its **Evidence Passport** |
| Six Modules | Per-module status, missing-data list, charts (one unit per axis), module table, findings, all calculations |
| Discovery Graph | Interactive network of sources, facts, events, metrics, calculations and hypotheses; edges labelled observed / inferred / contradictory / unverified |
| Promise-to-Cash Timeline | Targets and deadlines → milestones/announcements → financing → operating results → financial results |
| Contradiction Lab | Same metric/period with conflicting values (side by side, with the selection rule), and supporting vs opposing evidence per finding |
| Evidence Explorer | Searchable facts (passage, page, source, verification status, method), fact drill-down to calculations and findings, source table |
| Report Studio | Markdown and HTML report download, plus facts as CSV |

## How it works

```
company → identity resolution (data/companies.csv: identity metadata only, no findings)
  └─ round 1..N (N ≤ 3 by default)
       plan questions ─ search ─ fetch/parse (PDF via PyMuPDF → pdfplumber → pypdf fallback; HTML; text)
       ─ extract facts (rules for sentences and tables; optional LLM proposals kept only if grounded verbatim)
       ─ six modules (deterministic Python calculations, each linked to input facts)
       ─ hypotheses (one per signal key, revised across rounds) ─ counter-checks + counter-evidence queries
  └─ graph edges, optional number-guarded interpretations, report
```

- **Six modules** (`eia/modules/`): *Promise vs Reality* (targets vs actuals, required vs historical pace,
  capex step-up), *Green Growth* (capacity/generation/revenue CAGR, implied utilisation, divergence),
  *Capital & Cash* (leverage, coverage, cash conversion, FCF, debt vs EBITDA growth), *Hidden Risk*
  (composite of independent warnings plus receivable days and disclosed delays or downgrades), *Hidden
  Connections* (co-movement with ≥4 changes, commissioning vs reported capacity), and *Early Warning*
  (reversals, deceleration, same-quarter YoY, margin compression).
- **Evidence Passport** for every finding: supporting facts (value, period, scope, verbatim passage, source
  link, page, tier), calculations (formula, inputs, result, input fact ids), counter-checks run,
  counter-evidence, counterarguments, limitations, evidence strength, falsification condition and round history.
- **Storage:** SQLite (`data/eia.sqlite`) holds runs, sources, facts, calculations, a `calc_inputs` link table,
  hypotheses, relationships, research events and module results.

### Verification rules as implemented

- **Labels:** *verified fact* (value found verbatim in the cited passage), *unverified claim*, *calculated*,
  *hypothesis*, *interpretation*. Interpretations come from the LLM, never supply numbers, and are discarded if
  they contain any number not present in the evidence.
- **Units and periods:** units are normalised (MW, MU, ₹ crore incl. lakh / lakh-crore) and never guessed;
  foreign currency is never converted. Indian fiscal periods are handled, and ambiguous table columns are left
  unlabelled rather than guessed.
- **Scope and dates:** consolidated and standalone figures are never treated as conflicting; mixed-scope series
  are flagged. Future publication dates are ignored, and reports four or more years old are flagged.
- **Conflicts:** values that differ by more than 2% for the same metric, period and scope are flagged as
  contradictions. Any finding that uses a conflicted or unverified fact is capped at *Unresolved*.
- **Statuses:** *Supported* only after the counter-evidence search, with moderate or strong evidence and no
  material opposing evidence. *Weakened* or *Rejected* when counter-checks find opposing evidence.
  *Insufficient evidence* when data are missing. A signal that disappears after new evidence is rejected rather
  than silently dropped.
- **Causation:** never inferred. Correlations are labelled as associations and capped at *weak* strength on small
  samples, and composites state that co-occurrence does not imply a shared cause.
- **Bounds and failures:** research is bounded to 3 rounds by default. A failing source, search call or module is
  logged and the run continues; partial results are kept.

## Validation

See [`validation/README.md`](validation/README.md) for the full, honest record. In short:

- **Baseline on an unseen real company: failed** (0 facts) because of format gaps.
- **Second company, code frozen: partial**, including one materially wrong finding caused by an unlabelled ratio row.
- **Third company, code frozen: passed**, with conservative statuses.

All fixes were generic and are covered by tests on invented data.

## Project layout

```
app.py                     Streamlit dashboard (8 pages)
ui/theme.py                dark theme, status pills
eia/agent.py               research loop        eia/verification.py  hypotheses, counter-checks, grading
eia/extraction/            parsing, rule + LLM extraction, source classification
eia/modules/               six analytical modules       eia/calculations.py  deterministic calculations
eia/graph.py  views.py  report.py  demo.py  db.py  schema.py  metrics.py  periods.py  identity.py  providers/
scripts/research.py        CLI     scripts/validate_real_docs.sh   real-document regression run
tests/                     102 offline tests      validation/   transcribed real disclosures + results
```

## Known limitations

- Identity registry (`data/companies.csv`) covers about 40 listed energy names. Other companies can be researched
  as *unregistered*, with a warning.
- Extraction is rule-based. It is strong on financial tables and standard phrasing, weaker on charts, scanned PDFs
  (no OCR) and segment-level capacity prose. Group-level vs listed-entity scope is not detected automatically
  and is flagged as a limitation on target comparisons.
- Metric definitions differ across sources (e.g. aggregator "Operating Profit" vs company EBITDA/PBDIT). These are
  surfaced as contradictions, which conservatively keeps dependent findings unresolved.
- A table embedded in a filing that belongs to another company is not detected automatically. One such NSE PDF
  was found during validation and excluded by hand.
- Thresholds such as 5x leverage, 2x coverage and 1.5x pace are sector heuristics, documented in each module.
