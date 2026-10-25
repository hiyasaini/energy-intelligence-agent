"""Command-line research run.

Examples:
  python scripts/research.py --demo
  python scripts/research.py "Tata Power"                       # live: uses the search provider in .env
  python scripts/research.py KPIGREEN --doc file.pdf=https://original/url.pdf --no-search --out reports/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eia.agent import ResearchAgent, SeedDocument  # noqa: E402
from eia.config import get_settings  # noqa: E402
from eia.db import Store  # noqa: E402
from eia.demo import run_demo  # noqa: E402
from eia.identity import resolve, unregistered  # noqa: E402
from eia.providers.search import NullSearch  # noqa: E402
from eia.report import build_html, build_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Energy Intelligence Agent — command-line research run")
    ap.add_argument("company", nargs="?", help="company name or NSE symbol")
    ap.add_argument("--demo", action="store_true", help="run the synthetic demo")
    ap.add_argument("--doc", action="append", default=[],
                    help="local document to include; optionally 'path=original_url' to keep the source URL")
    ap.add_argument("--url", action="append", default=[], help="document URL to fetch and include")
    ap.add_argument("--no-search", action="store_true", help="do not use the search provider")
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--db", default=None, help="SQLite path (default from .env)")
    ap.add_argument("--out", default=None, help="directory for Markdown + HTML reports")
    ap.add_argument("--allow-unregistered", action="store_true")
    a = ap.parse_args()

    s = get_settings(db_path=a.db) if a.db else get_settings()
    store = Store(s.db_path)
    log = lambda stage, msg, frac: print(f"[{stage:8}] {msg}")  # noqa: E731
    if a.demo:
        out = run_demo(store, s, progress=log, max_rounds=a.rounds)
    else:
        if not a.company:
            ap.error("company is required unless --demo")
        res = resolve(a.company)
        if res.status == "resolved":
            company = res.company
        elif res.status == "ambiguous":
            print("Ambiguous company; candidates:")
            for c, sc in res.candidates:
                print(f"  {c.name} (NSE {c.nse})  score {sc:.2f}")
            return 2
        elif a.allow_unregistered:
            company = unregistered(a.company)
        else:
            print(res.message + " Use --allow-unregistered to proceed.")
            return 2
        seeds = []
        for d in a.doc:
            path, _, url = d.partition("=")
            p = Path(path)
            data = p.read_bytes()
            ct = "application/pdf" if data[:5] == b"%PDF-" else ("text/html" if p.suffix in (".html", ".htm") else "text/plain")
            seeds.append(SeedDocument(p.name, data, url, ct))
        agent = ResearchAgent(store, s, search=NullSearch() if a.no_search else None, progress=log)
        out = agent.research(company, "live", seed_documents=seeds, seed_urls=a.url, max_rounds=a.rounds)
    print(f"\nRun {out.run_id}: {out.status}, {out.rounds} round(s), {out.n_sources} source(s), {out.n_facts} fact(s), "
          f"{out.n_hypotheses} finding(s)")
    if a.out:
        od = Path(a.out)
        od.mkdir(parents=True, exist_ok=True)
        (od / f"{out.run_id}.md").write_text(build_markdown(store, out.run_id), encoding="utf-8")
        (od / f"{out.run_id}.html").write_text(build_html(store, out.run_id), encoding="utf-8")
        print(f"Reports written to {od}/{out.run_id}.md and .html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
