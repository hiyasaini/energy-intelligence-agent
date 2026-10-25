"""Shared module plumbing: the analysis context and the result/signal containers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..calculations import Calculator, Point, Series, build_series
from ..metrics import METRICS, metric_label
from ..periods import is_annual, period_sort_key
from ..schema import (Calculation, Company, Fact, FactStatus, FactType, Relationship, RelLabel, Source,
                      SourceTier)


@dataclass
class Signal:
    """A candidate finding emitted by a module; becomes (or revises) a Hypothesis."""
    key: str
    module: str
    title: str
    statement: str
    direction: str = "risk"              # risk | opportunity | neutral
    severity: float = 0.5                # 0..1, used for ranking only
    supporting_fact_ids: list[str] = field(default_factory=list)
    calc_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    falsification: str = ""
    counter_checks: list[str] = field(default_factory=list)
    counter_queries: list[str] = field(default_factory=list)
    insufficient: bool = False
    max_strength: str = ""               # cap on evidence strength (e.g. small-sample statistics)
    params: dict = field(default_factory=dict)  # numbers the counter-checks need (from calculations only)


@dataclass
class ModuleResult:
    key: str
    name: str
    status: str = "ok"                   # ok | partial | insufficient_data
    summary: str = ""
    rows: list[dict] = field(default_factory=list)
    series: dict[str, Series] = field(default_factory=dict)
    signals: list[Signal] = field(default_factory=list)
    calcs: list[Calculation] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class AnalysisContext:
    def __init__(self, run_id: str, company: Company, facts: list[Fact], sources: list[Source]):
        self.run_id = run_id
        self.company = company
        from ..business import excluded_metrics
        drop = excluded_metrics(company.segment if company else "")
        self.facts = [f for f in facts if f.status != FactStatus.rejected and f.metric not in drop]
        self.sources = {s.id: s for s in sources}
        self.tiers: dict[str, SourceTier] = {s.id: s.tier for s in sources}
        self.facts_by_id = {f.id: f for f in self.facts}
        self._cache: dict[tuple, Series] = {}
        self.peers: list = []            # PeerProfile list (live runs only); empty means no peer check
        self._own_profile: Optional[dict] = None

    def own_profile(self) -> dict:
        """The company's comparable figures, computed exactly as they are for peers."""
        if self._own_profile is None:
            from ..peers import profile
            self._own_profile = profile(self.facts, self.tiers)
        return self._own_profile

    def _raw_series(self, metric: str, periodicity: str = "annual") -> Series:
        k = ("raw", metric, periodicity)
        if k not in self._cache:
            s = build_series(self.facts, metric, self.tiers, periodicity)
            from ..sanity import ABS_MAX, apply
            if metric in ABS_MAX:
                from ..business import business_type

                def revenue(period: str):
                    rev = self._raw_series("revenue_cr")
                    r = rev.get(period) or (rev.points[-1] if rev.points else None)
                    return r.value if r else None
                s = apply(metric, s, business_type(self.company.segment if self.company else ""), revenue)
            self._cache[k] = s
        return self._cache[k]

    def series(self, metric: str, periodicity: str = "annual") -> Series:
        k = (metric, periodicity)
        if k not in self._cache:
            s = self._raw_series(metric, periodicity)
            pair = {"installed_capacity_mw": "renewable_capacity_mw", "renewable_capacity_mw": "installed_capacity_mw"}
            if metric in pair:
                # renewable capacity cannot exceed total capacity: a period where it does holds two figures that
                # describe different things (one is a pipeline, a group total or a single segment) - use neither
                import copy
                s = copy.deepcopy(s)
                other = self._raw_series(pair[metric], periodicity)
                for pt in list(s.points):
                    o = other.get(pt.period)
                    if not o:
                        continue
                    ren, inst = (pt.value, o.value) if metric == "renewable_capacity_mw" else (o.value, pt.value)
                    if ren > inst * 1.001:
                        s.points = [p for p in s.points if p is not pt]
                        reason = (f"renewable capacity {ren:,.0f} MW exceeds total installed capacity {inst:,.0f} MW in "
                                  f"{pt.period}; the two figures describe different things, so neither is used.")
                        s.excluded.append({"period": pt.period, "value": pt.value, "fact_id": pt.fact_id, "reason": reason})
                        s.warnings.append(f"{metric} {pt.period}: {reason}")
            self._cache[k] = s
        return self._cache[k]

    def latest_point(self, metric: str) -> Optional[Point]:
        """Most recent point across annual and quarterly series (for stock metrics)."""
        pts = list(self.series(metric).points)
        if metric in METRICS and METRICS[metric].kind == "stock":
            pts += list(self.series(metric, "quarterly").points)
        if not pts:
            return None
        from ..periods import period_end
        return max(pts, key=lambda p: (period_end(p.period) or "", is_annual(p.period)))

    def targets(self, metrics: Optional[list[str]] = None) -> list[Fact]:
        return [f for f in self.facts if f.fact_type == FactType.target and f.value is not None and f.target_year
                and (metrics is None or f.metric in metrics)]

    def events(self, categories: Optional[list[str]] = None) -> list[Fact]:
        return [f for f in self.facts if f.fact_type == FactType.event
                and (categories is None or f.event_category in categories)]

    def has(self, metric: str) -> bool:
        return len(self.series(metric)) > 0 or len(self.series(metric, "quarterly")) > 0

    def calculator(self, module: str) -> Calculator:
        return Calculator(self.run_id, module)

    def conflict_relationships(self, series: Series, module: str) -> list[Relationship]:
        rels = []
        for c in series.conflicts:
            for i in range(len(c.fact_ids) - 1):
                rels.append(Relationship(run_id=self.run_id, src_type="fact", src_id=c.fact_ids[i], dst_type="fact",
                                         dst_id=c.fact_ids[i + 1], relation="contradicts", label=RelLabel.contradictory,
                                         note=f"{metric_label(c.metric)} {c.period}: values differ by "
                                              f"{c.rel_diff * 100:.1f}% ({', '.join(f'{v:,.2f}' for v in c.values)})"))
        return rels


def fmt(v: Optional[float], unit: str = "", nd: int = 1) -> str:
    if v is None:
        return "n/a"
    u = {"INR_cr": " ₹ cr", "MW": " MW", "MU": " MU", "%": "%", "x": "x"}.get(unit, f" {unit}" if unit else "")
    if abs(v) >= 1000:
        return f"{v:,.0f}{u}"
    return f"{v:,.{nd}f}{u}"


def latest_two(series: Series) -> tuple[Optional[Point], Optional[Point]]:
    pts = sorted(series.points, key=lambda p: period_sort_key(p.period))
    if len(pts) < 2:
        return None, (pts[-1] if pts else None)
    return pts[-2], pts[-1]


def same_quarter_last_year(series: Series, p: Point) -> Optional[Point]:
    import re
    m = re.fullmatch(r"Q([1-4])FY(\d{4})", p.period)
    if not m:
        return None
    return series.get(f"Q{m.group(1)}FY{int(m.group(2)) - 1}")
