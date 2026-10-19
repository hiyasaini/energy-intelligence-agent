"""Test helpers: build facts/contexts without any network access."""
from __future__ import annotations

from eia.modules import AnalysisContext
from eia.periods import period_end
from eia.schema import Company, Fact, FactStatus, FactType, Scope, Source, SourceTier

CO = Company(name="Testco Power Ltd", nse="TESTCO")


def src(i: str = "s1", tier: SourceTier = SourceTier.company, title: str = "Testco annual report") -> Source:
    return Source(id=i, run_id="r", url=f"https://testco.example/{i}.pdf", title=title, tier=tier, fetch_status="ok")


def fact(metric: str, period: str, value: float, unit: str, source_id: str = "s1", **kw) -> Fact:
    d = dict(run_id="r", metric=metric, value=value, unit=unit, raw_value=f"{value:,.0f}", period=period,
             period_end=period_end(period), scope=Scope.consolidated, source_id=source_id, page=1,
             passage=f"{metric} {value:,.0f}", status=FactStatus.source_verified, confidence=0.7)
    d.update(kw)
    return Fact(**d)


def target(metric: str, value: float, unit: str, year: int, period: str = "FY2025", source_id: str = "s1") -> Fact:
    return fact(metric, period, value, unit, source_id, fact_type=FactType.target, target_year=year)


def ctx(facts: list[Fact], sources: list[Source] | None = None) -> AnalysisContext:
    return AnalysisContext("r", CO, facts, sources or [src("s1"), src("s2", title="Testco presentation")])


def annual(metric: str, unit: str, values: dict[int, float], source_id: str = "s1") -> list[Fact]:
    return [fact(metric, f"FY{y}", v, unit, source_id) for y, v in values.items()]
