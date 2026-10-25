"""Print every extracted fact for one metric and period from the validation documents (diagnostics).

    python scripts/diag_facts.py KPIGREEN revenue_cr FY2026
"""
import os
import sys
from pathlib import Path

os.environ.update({"EIA_DIRECT_SOURCES": "off", "EIA_SEARCH_PROVIDER": "none", "EIA_LLM_PROVIDER": "none"})

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from eia.agent import ResearchAgent, SeedDocument  # noqa: E402
from eia.config import get_settings  # noqa: E402
from eia.db import Store  # noqa: E402
from eia.identity import resolve  # noqa: E402
from eia.providers.llm import NullLLM  # noqa: E402
from eia.providers.search import NullSearch  # noqa: E402
from test_real_documents import SETS, V  # noqa: E402

sym, metric, period = (sys.argv[1:4] + ["KPIGREEN", "revenue_cr", "FY2026"][len(sys.argv) - 1:])[:3]
st = Store(":memory:")
seeds = [SeedDocument(Path(p).name, (V / p).read_bytes(), u, "text/plain") for p, u in SETS[sym]]
o = ResearchAgent(st, get_settings(), search=NullSearch(), llm=NullLLM(), direct=None).research(
    resolve(sym).company, seed_documents=seeds)
srcs = {s.id: s for s in st.sources(o.run_id)}
print(sys.version)
for f in st.facts(o.run_id):
    if f.metric == metric and f.period == period:
        print(f"{f.value:>12.2f} {f.scope.value:13} {srcs[f.source_id].title[:45]:45} | {f.label} | {f.passage[:110]!r}")
