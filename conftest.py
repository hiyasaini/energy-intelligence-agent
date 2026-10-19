import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests never touch the network: key-free sources and market data are off unless a test injects fakes."""
    monkeypatch.setenv("EIA_DIRECT_SOURCES", "off")
    monkeypatch.setenv("EIA_MARKET_DATA", "none")
