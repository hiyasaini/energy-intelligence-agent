import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Offline for the WHOLE session, set before any fixture runs (module-scoped fixtures build agents before the
# per-test fixture below, so on a machine with internet they would otherwise read live NSE filings).
OFFLINE = {"EIA_DIRECT_SOURCES": "off", "EIA_MARKET_DATA": "none", "EIA_SEARCH_PROVIDER": "none",
           "EIA_LLM_PROVIDER": "none"}
os.environ.update(OFFLINE)


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests never touch the network: key-free sources and market data are off unless a test injects fakes."""
    for k, v in OFFLINE.items():
        monkeypatch.setenv(k, v)
