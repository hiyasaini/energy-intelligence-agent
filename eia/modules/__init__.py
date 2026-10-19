"""Six generic analytical modules. Each takes an AnalysisContext and returns a ModuleResult."""
from __future__ import annotations

from . import capital_cash, early_warning, green_growth, hidden_connections, hidden_risk, promise_reality
from .base import AnalysisContext, ModuleResult, Signal

MODULE_ORDER = [
    (promise_reality.KEY, promise_reality.NAME),
    (green_growth.KEY, green_growth.NAME),
    (capital_cash.KEY, capital_cash.NAME),
    (hidden_risk.KEY, hidden_risk.NAME),
    (hidden_connections.KEY, hidden_connections.NAME),
    (early_warning.KEY, early_warning.NAME),
]
MODULE_NAMES = dict(MODULE_ORDER)


def run_all(ctx: AnalysisContext) -> dict[str, ModuleResult]:
    """Run modules; a failing module is reported, never allowed to stop the others."""
    out: dict[str, ModuleResult] = {}
    upstream: list[Signal] = []
    for mod in (promise_reality, green_growth, capital_cash, early_warning, hidden_connections):
        out[mod.KEY] = _safe(mod.KEY, mod.NAME, lambda m=mod: m.run(ctx))
        upstream += out[mod.KEY].signals
    out[hidden_risk.KEY] = _safe(hidden_risk.KEY, hidden_risk.NAME, lambda: hidden_risk.run(ctx, upstream))
    return {k: out[k] for k, _ in MODULE_ORDER}


def _safe(key: str, name: str, fn) -> ModuleResult:
    try:
        return fn()
    except Exception as e:  # preserve partial results
        r = ModuleResult(key, name, status="error", summary=f"Module failed: {type(e).__name__}: {e}")
        return r


__all__ = ["AnalysisContext", "ModuleResult", "Signal", "MODULE_ORDER", "MODULE_NAMES", "run_all"]
