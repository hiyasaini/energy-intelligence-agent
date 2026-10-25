"""Deterministic financial calculations.

Rules:
  * every result is a Calculation carrying formula, input values and input fact ids;
  * missing inputs -> status 'insufficient_data', result None (never a guessed value);
  * unit / scope / period mismatches -> status 'incompatible' (or 'warning' for scope mixing).
"""
from __future__ import annotations

import math
from datetime import date
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .metrics import metric_dimension, CANONICAL_UNIT
from .periods import is_annual, is_quarter, period_end, period_sort_key
from .schema import TIER_WEIGHT, Calculation, Fact, FactStatus, FactType, Scope, SourceTier

CONFLICT_TOLERANCE = 0.02  # 2% relative difference treated as a genuine disagreement
MIN_CORR_PERIODS = 5       # correlation needs >= 4 year-on-year changes before it is reported
STALE_YEARS = 10           # annual points older than this (vs the latest point) are not used
ISOLATION_GAP = 5          # a point separated from the rest of the series by more years than this is not used
JUMP_FACTOR = 5.0          # a single-source value 5x above / below its neighbours needs corroboration
SIGNED_METRICS = {"pat_cr", "cfo_cr", "net_debt_cr"}   # can legitimately flip sign or swing widely


@dataclass
class Point:
    period: str
    value: float
    fact_id: str
    scope: str
    unit: str


@dataclass
class Conflict:
    metric: str
    period: str
    fact_ids: list[str]
    values: list[float]
    scope: str
    rel_diff: float


@dataclass
class Series:
    metric: str
    unit: str
    points: list[Point] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)   # points held out by the plausibility guards

    @property
    def periods(self) -> list[str]:
        return [p.period for p in self.points]

    @property
    def values(self) -> list[float]:
        return [p.value for p in self.points]

    def get(self, period: str) -> Optional[Point]:
        return next((p for p in self.points if p.period == period), None)

    def __len__(self) -> int:
        return len(self.points)


def _rank(f: Fact, tiers: dict[str, SourceTier], scope_pref: list[str], coverage: Optional[dict] = None) -> tuple:
    tier = tiers.get(f.source_id, SourceTier.unknown)
    return (
        scope_pref.index(f.scope.value) if f.scope.value in scope_pref else 9,
        # the source that reports this metric for the most periods gives the most consistent trend
        # (same definitions every year); single-period mentions elsewhere become cross-checks
        -(coverage or {}).get(f.source_id, 0),
        0 if f.status == FactStatus.source_verified else 1,
        1 if f.period_inferred else 0,
        -TIER_WEIGHT.get(tier, 0.3),
        -f.confidence,
    )


def build_series(facts: list[Fact], metric: str, tiers: dict[str, SourceTier],
                 periodicity: str = "annual", today: Optional[date] = None) -> Series:
    want = is_annual if periodicity == "annual" else is_quarter
    dim = metric_dimension(metric)
    unit = CANONICAL_UNIT.get(dim or "", "")
    cands = [f for f in facts if f.metric == metric and f.fact_type == FactType.reported and f.value is not None
             and f.status != FactStatus.rejected and want(f.period) and (not unit or f.unit == unit)]
    s = Series(metric=metric, unit=unit)
    cutoff = (today or date.today()).isoformat()
    future = sorted({f.period for f in cands if (period_end(f.period) or "") > cutoff}, key=period_sort_key)
    if future:   # a period that has not ended yet is a projection, a plan or a trailing-twelve-month column
        s.warnings.append(f"{metric}: {', '.join(future)} not yet ended; figures for it are not used as actuals.")
        cands = [f for f in cands if f.period not in future]
    if not cands:
        return s
    # dominant scope: the known scope reported for the most distinct periods; consolidated wins ties
    counts = defaultdict(int)
    for sc in {f.scope.value for f in cands if f.scope != Scope.unknown}:
        counts[sc] = len({f.period for f in cands if f.scope.value == sc})
    if counts:
        dominant = max(counts, key=lambda k: (counts[k], k == "consolidated"))
    else:
        dominant = "unknown"
    other = "standalone" if dominant == "consolidated" else "consolidated"
    scope_pref = [dominant, "unknown", other]

    by_period: dict[str, list[Fact]] = defaultdict(list)
    for f in cands:
        by_period[f.period].append(f)
    coverage: dict[str, int] = defaultdict(int)
    for sid in {f.source_id for f in cands}:
        coverage[sid] = len({f.period for f in cands if f.source_id == sid})
    used_scopes = set()
    for period in sorted(by_period, key=period_sort_key):
        group = sorted(by_period[period], key=lambda f: _rank(f, tiers, scope_pref, coverage))
        by_period[period] = group     # keep the ranked order: the plausibility guard falls back along it
        best = group[0]
        used_scopes.add(best.scope.value)
        s.points.append(Point(period, float(best.value), best.id, best.scope.value, best.unit))
        # conflicts: same period, comparable scope, materially different values
        comparable = [f for f in group if f.scope == best.scope or Scope.unknown in (f.scope, best.scope)]
        vals = [float(f.value) for f in comparable]
        if len(vals) > 1:
            lo, hi = min(vals), max(vals)
            denom = max(abs(hi), abs(lo), 1e-9)
            rd = (hi - lo) / denom
            if rd > CONFLICT_TOLERANCE:
                s.conflicts.append(Conflict(metric, period, [f.id for f in comparable], vals, best.scope.value, rd))
    _plausibility(s, by_period, periodicity)
    known = used_scopes - {"unknown"}
    if len(known) > 1:
        s.warnings.append(f"{metric}: series mixes consolidated and standalone figures; comparisons are indicative only.")
    if "unknown" in used_scopes and known:
        s.warnings.append(f"{metric}: some periods have unstated reporting scope.")
    return s


def _year(period: str) -> int:
    return period_sort_key(period)[0]


def _hold_out(s: Series, pt: Point, reason: str) -> None:
    s.points = [p for p in s.points if p is not pt]
    s.excluded.append({"period": pt.period, "value": pt.value, "fact_id": pt.fact_id, "reason": reason})
    s.warnings.append(f"{s.metric} {pt.period}: {reason}")


def _corroborated(pt: Point, group: list[Fact]) -> bool:
    """True if at least two different sources report (within 2%) the value used for this period."""
    srcs = {f.source_id for f in group if f.value is not None and pt.value and
            abs(float(f.value) - pt.value) <= CONFLICT_TOLERANCE * abs(pt.value)}
    return len(srcs) >= 2


def _plausibility(s: Series, by_period: dict[str, list[Fact]], periodicity: str) -> None:
    """Generic guards against misread periods and units. Points are held out (and listed), never altered."""
    if len(s.points) < 2:
        return
    if periodicity == "annual":
        latest = _year(s.points[-1].period)
        for pt in [p for p in s.points if _year(p.period) < latest - STALE_YEARS]:
            _hold_out(s, pt, f"more than {STALE_YEARS} years older than the latest figure; not used in trends "
                             "(often a misread year).")
        # an old point separated from the rest by a long gap
        while len(s.points) >= 3 and _year(s.points[1].period) - _year(s.points[0].period) > ISOLATION_GAP:
            _hold_out(s, s.points[0], f"separated from the rest of the series by more than {ISOLATION_GAP} years; "
                                      "not used in trends.")
    if s.metric in SIGNED_METRICS:
        _signed_fallback(s, by_period)
        return
    for i, pt in list(enumerate(s.points)):
        if pt not in s.points:
            continue
        idx = s.points.index(pt)
        neigh = [p.value for j, p in enumerate(s.points) if j != idx and abs(j - idx) <= 2]
        if len(neigh) < 2 or pt.value <= 0 or any(v <= 0 for v in neigh):
            continue
        ref = float(np.median(neigh))
        ratio = pt.value / ref
        if (ratio > JUMP_FACTOR or ratio < 1 / JUMP_FACTOR) and not _corroborated(pt, by_period.get(pt.period, [])):
            alt = next((f for f in by_period.get(pt.period, []) if f.id != pt.fact_id and f.value and
                        1 / JUMP_FACTOR <= float(f.value) / ref <= JUMP_FACTOR), None)
            if alt is not None:   # another source for the same period agrees with the neighbours: use it
                s.excluded.append({"period": pt.period, "value": pt.value, "fact_id": pt.fact_id,
                                   "reason": f"{ratio:.2f}x the neighbouring years; replaced by another source's "
                                             f"figure for the same period ({float(alt.value):,.2f})."})
                pt.value, pt.fact_id, pt.scope, pt.unit = float(alt.value), alt.id, alt.scope.value, alt.unit
                continue
            _hold_out(s, pt, f"value is {ratio:.2f}x the neighbouring years and comes from a single source; held out "
                             "of calculations until a second source confirms it (often a part-year figure or a "
                             "misread unit).")


def _signed_fallback(s: Series, by_period: dict[str, list[Fact]]) -> None:
    """Signed metrics (profit, cash flow) may swing, so they are never held out; but when the chosen figure is far
    out of scale with its neighbours and another source for the same period is in scale, that source is used."""
    for idx, pt in enumerate(s.points):
        neigh = [abs(p.value) for j, p in enumerate(s.points) if j != idx and abs(j - idx) <= 2 and p.value]
        if len(neigh) < 2 or not pt.value:
            continue
        ref = float(np.median(neigh))
        ratio = abs(pt.value) / ref if ref else 1.0
        if 1 / JUMP_FACTOR <= ratio <= JUMP_FACTOR:
            continue
        alt = next((f for f in by_period.get(pt.period, []) if f.id != pt.fact_id and f.value and
                    1 / JUMP_FACTOR <= abs(float(f.value)) / ref <= JUMP_FACTOR), None)
        if alt is not None:
            s.excluded.append({"period": pt.period, "value": pt.value, "fact_id": pt.fact_id,
                               "reason": f"{ratio:.2f}x the scale of neighbouring years; replaced by another source's "
                                         f"figure for the same period ({float(alt.value):,.2f})."})
            pt.value, pt.fact_id, pt.scope, pt.unit = float(alt.value), alt.id, alt.scope.value, alt.unit


PHYS_JUMP = 4.0          # physical volumes (MW, MU, tonnes, km) do not change 4-fold in a year at listed companies
PHYS_CAGR_MAX = 1.5      # ... nor grow faster than 150% a year on average


def _physical(unit: str) -> bool:
    return bool(unit) and unit not in ("INR_cr", "%", "x", "days", "score")


class Calculator:
    """Collects Calculation records for one run/module."""

    def __init__(self, run_id: str, module: str):
        self.run_id = run_id
        self.module = module
        self.records: list[Calculation] = []

    def _rec(self, **kw) -> Calculation:
        c = Calculation(run_id=self.run_id, module=self.module, **kw)
        if c.result is not None and (math.isnan(c.result) or math.isinf(c.result)):
            c.result, c.status = None, "insufficient_data"
            c.notes = (c.notes + " Non-finite result suppressed.").strip()
        self.records.append(c)
        return c

    def insufficient(self, name: str, formula: str, missing: str, period: str = "") -> Calculation:
        return self._rec(name=name, formula=formula, status="insufficient_data", period=period,
                         notes=f"Insufficient evidence: {missing}")

    # -- primitives ---------------------------------------------------------------------
    def growth(self, name: str, prev: Optional[Point], cur: Optional[Point]) -> Calculation:
        f = "(current - previous) / |previous|"
        if not prev or not cur:
            return self.insufficient(name, f, "needs two periods")
        if prev.unit != cur.unit:
            return self._rec(name=name, formula=f, status="incompatible", notes="unit mismatch",
                             input_fact_ids=[prev.fact_id, cur.fact_id])
        if prev.value <= 0:
            return self.insufficient(name, f, "growth is not meaningful from a zero or negative base", cur.period)
        r = (cur.value - prev.value) / abs(prev.value)
        if _physical(cur.unit) and not (1 / PHYS_JUMP <= cur.value / prev.value <= PHYS_JUMP):
            return self.insufficient(name, f, f"not meaningful: {prev.period} and {cur.period} figures differ "
                                              f"{max(cur.value / prev.value, prev.value / cur.value):.0f}-fold, so they "
                                              "do not describe the same assets", cur.period)
        st, note = "ok", ""
        if prev.scope != cur.scope and "unknown" not in (prev.scope, cur.scope):
            st, note = "warning", "scope differs between periods"
        return self._rec(name=name, formula=f, input_fact_ids=[prev.fact_id, cur.fact_id],
                         inputs={f"{prev.period}": prev.value, f"{cur.period}": cur.value},
                         result=r * 100, unit="%", period=cur.period, status=st, notes=note)

    def cagr(self, name: str, series: Series) -> Calculation:
        f = "(last / first)^(1/years) - 1"
        pts = [p for p in series.points if is_annual(p.period)]
        if len(pts) < 2:
            return self.insufficient(name, f, f"needs >=2 annual points for {series.metric}")
        first, last = pts[0], pts[-1]
        years = period_sort_key(last.period)[0] - period_sort_key(first.period)[0]
        if years <= 0 or first.value <= 0 or last.value <= 0:
            return self.insufficient(name, f, "non-positive values or zero span", last.period)
        r = (last.value / first.value) ** (1 / years) - 1
        if _physical(last.unit) and r > PHYS_CAGR_MAX:
            return self.insufficient(name, f, f"not meaningful: {r * 100:,.0f}% a year implies the first and last "
                                              "figures describe different assets", last.period)
        return self._rec(name=name, formula=f, input_fact_ids=[first.fact_id, last.fact_id],
                         inputs={first.period: first.value, last.period: last.value, "years": years},
                         result=r * 100, unit="%", period=f"{first.period}-{last.period}")

    def ratio(self, name: str, num: Optional[Point], den: Optional[Point], unit: str = "x",
              scale: float = 1.0, formula: str = "") -> Calculation:
        f = formula or "numerator / denominator"
        if not num or not den:
            return self.insufficient(name, f, "numerator or denominator missing",
                                     (num or den).period if (num or den) else "")
        if num.period != den.period:
            return self._rec(name=name, formula=f, status="incompatible", input_fact_ids=[num.fact_id, den.fact_id],
                             notes=f"period mismatch {num.period} vs {den.period}")
        if den.value == 0:
            return self.insufficient(name, f, "denominator is zero", num.period)
        st, note = "ok", ""
        if num.scope != den.scope and "unknown" not in (num.scope, den.scope):
            st, note = "warning", "numerator and denominator have different reporting scope"
        return self._rec(name=name, formula=f, input_fact_ids=[num.fact_id, den.fact_id],
                         inputs={"numerator": num.value, "denominator": den.value},
                         result=num.value / den.value * scale, unit=unit, period=num.period, status=st, notes=note)

    def difference(self, name: str, a: Optional[Point], b: Optional[Point], formula: str = "a - b") -> Calculation:
        if not a or not b:
            return self.insufficient(name, formula, "operand missing")
        if a.unit != b.unit:
            return self._rec(name=name, formula=formula, status="incompatible", notes="unit mismatch",
                             input_fact_ids=[a.fact_id, b.fact_id])
        if a.period != b.period:
            return self._rec(name=name, formula=formula, status="incompatible",
                             notes=f"period mismatch {a.period} vs {b.period}", input_fact_ids=[a.fact_id, b.fact_id])
        return self._rec(name=name, formula=formula, input_fact_ids=[a.fact_id, b.fact_id],
                         inputs={"a": a.value, "b": b.value}, result=a.value - b.value, unit=a.unit, period=a.period)

    def change(self, name: str, prev: Optional[Point], cur: Optional[Point]) -> Calculation:
        """Absolute change between two periods of the same metric (e.g. capacity added in a year)."""
        f = "current - previous"
        if not prev or not cur:
            return self.insufficient(name, f, "needs two periods")
        if prev.unit != cur.unit:
            return self._rec(name=name, formula=f, status="incompatible", notes="unit mismatch",
                             input_fact_ids=[prev.fact_id, cur.fact_id])
        if period_sort_key(cur.period) <= period_sort_key(prev.period):
            return self._rec(name=name, formula=f, status="incompatible", notes="periods out of order",
                             input_fact_ids=[prev.fact_id, cur.fact_id])
        st, note = "ok", ""
        if prev.scope != cur.scope and "unknown" not in (prev.scope, cur.scope):
            st, note = "warning", "scope differs between periods"
        return self._rec(name=name, formula=f, input_fact_ids=[prev.fact_id, cur.fact_id],
                         inputs={prev.period: prev.value, cur.period: cur.value}, result=cur.value - prev.value,
                         unit=cur.unit, period=cur.period, status=st, notes=note)

    def slope(self, name: str, series: Series) -> Calculation:
        """Least-squares slope per period, expressed as % of the series mean."""
        f = "OLS slope of value on period index / mean(value)"
        if len(series) < 3:
            return self.insufficient(name, f, f"needs >=3 periods for {series.metric}")
        y = np.array(series.values, dtype=float)
        x = np.arange(len(y), dtype=float)
        m = float(np.polyfit(x, y, 1)[0])
        mean = float(np.mean(np.abs(y)))
        if mean == 0:
            return self.insufficient(name, f, "zero mean")
        return self._rec(name=name, formula=f, input_fact_ids=[p.fact_id for p in series.points],
                         inputs={p.period: p.value for p in series.points},
                         result=m / mean * 100, unit="% of mean per period", period=series.points[-1].period)

    def target_progress(self, name: str, target: Fact, current: Optional[Point],
                        hist_rate: Optional[Calculation]) -> list[Calculation]:
        """Achievement %, remaining gap and required annual run-rate vs historical run-rate."""
        out = []
        f1 = "current / target"
        if current is None or target.value in (None, 0):
            out.append(self.insufficient(name + " — achievement", f1, "current value or target missing"))
            return out
        if target.unit != current.unit:
            out.append(self._rec(name=name + " — achievement", formula=f1, status="incompatible",
                                 notes=f"unit mismatch {target.unit} vs {current.unit}",
                                 input_fact_ids=[target.id, current.fact_id]))
            return out
        ach = self._rec(name=name + " — achievement", formula=f1, input_fact_ids=[target.id, current.fact_id],
                        inputs={"target": target.value, f"current ({current.period})": current.value},
                        result=current.value / target.value * 100, unit="%", period=current.period)
        out.append(ach)
        cur_fy = period_sort_key(current.period)[0]
        if target.target_year:
            years_left = target.target_year - cur_fy
            f2 = "(target - current) / years_remaining"
            if years_left <= 0:
                out.append(self._rec(name=name + " — required run-rate", formula=f2, status="ok",
                                     input_fact_ids=[target.id, current.fact_id],
                                     inputs={"target": target.value, "current": current.value,
                                             "target_year": target.target_year, "as_of": current.period},
                                     result=target.value - current.value, unit=target.unit + " shortfall at deadline",
                                     period=current.period, notes="target date has passed or is the current year"))
            else:
                req = (target.value - current.value) / years_left
                ids = [target.id, current.fact_id]
                inputs = {"target": target.value, "current": current.value, "years_remaining": years_left}
                notes = ""
                if hist_rate is not None and hist_rate.result is not None:
                    inputs["historical_run_rate"] = hist_rate.result
                    notes = "Compare with historical run-rate calculation " + hist_rate.id
                out.append(self._rec(name=name + " — required run-rate", formula=f2, input_fact_ids=ids,
                                     input_calc_ids=[hist_rate.id] if hist_rate else [], inputs=inputs,
                                     result=req, unit=target.unit + "/yr", period=current.period, notes=notes))
        return out

    def avg_annual_addition(self, name: str, series: Series) -> Calculation:
        f = "(last - first) / years"
        pts = [p for p in series.points if is_annual(p.period)]
        if len(pts) < 2:
            return self.insufficient(name, f, "needs >=2 annual points")
        first, last = pts[0], pts[-1]
        yrs = period_sort_key(last.period)[0] - period_sort_key(first.period)[0]
        if yrs <= 0:
            return self.insufficient(name, f, "zero span")
        return self._rec(name=name, formula=f, input_fact_ids=[first.fact_id, last.fact_id],
                         inputs={first.period: first.value, last.period: last.value, "years": yrs},
                         result=(last.value - first.value) / yrs, unit=series.unit + "/yr",
                         period=f"{first.period}-{last.period}")

    def correlation(self, name: str, a: Series, b: Series, lag: int = 0) -> Calculation:
        f = f"Pearson r of YoY changes (b lagged {lag} period)"
        pa = {p.period: p for p in a.points}
        pb = {p.period: p for p in b.points}
        common = sorted(set(pa) & set(pb), key=period_sort_key)
        if len(common) < MIN_CORR_PERIODS + lag:
            return self.insufficient(name, f, f"needs >= {MIN_CORR_PERIODS + lag} overlapping periods")
        da = np.diff([pa[p].value for p in common])
        db = np.diff([pb[p].value for p in common])
        if lag:
            da, db = da[:-lag], db[lag:]
        if len(da) < MIN_CORR_PERIODS - 1 or np.std(da) == 0 or np.std(db) == 0:
            return self.insufficient(name, f, "too few or constant changes")
        r = float(np.corrcoef(da, db)[0, 1])
        return self._rec(name=name, formula=f,
                         input_fact_ids=[pa[p].fact_id for p in common] + [pb[p].fact_id for p in common],
                         inputs={"periods": ", ".join(common), "n_changes": len(da)}, result=r, unit="r",
                         period=common[-1], notes="Correlation does not establish causation.")
