#!/usr/bin/env bash
# Re-run the real-document validation sets (transcribed public disclosures) offline. Usage: scripts/validate_real_docs.sh OUTDIR
set -e
OUT=${1:-validation/out}; mkdir -p "$OUT"
cd "$(dirname "$0")/.."
K=validation/kpigreen
python3 scripts/research.py KPIGREEN --no-search --db "$OUT/kpigreen.sqlite" --out "$OUT/kpigreen" \
 --doc $K/ar_fy2025_nse.txt=https://nsearchives.nseindia.com/annual_reports/AR_28496_KPIGREEN_2024_2025_A_23853547_04092025205945.pdf \
 --doc $K/results_fy2026_consolidated_nse.txt=https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_155932_06052026224222_iXBRL_WEB.html \
 --doc $K/results_fy2026_standalone_nse.txt=https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_155931_06052026224125_iXBRL_WEB.html \
 --doc $K/screener_consolidated.txt=https://www.screener.in/company/KPIGREEN/consolidated/
T=validation/torrentpower
python3 scripts/research.py TORNTPOWER --no-search --db "$OUT/torrentpower.sqlite" --out "$OUT/torrentpower" \
 --doc $T/results_fy2026_consolidated_nse.txt=https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_157002_12052026190955_iXBRL_WEB.html \
 --doc $T/investor_presentation_q1fy27_nse.txt=https://nsearchives.nseindia.com/corporate/TORNTPOWER_03082026172921_Investor_Presentation.pdf \
 --doc $T/screener_consolidated.txt=https://www.screener.in/company/TORNTPOWER/consolidated/
