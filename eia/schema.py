"""Shared, company-agnostic data model.

Epistemic categories are explicit so the UI and report can never blur them:
  * Fact (status=source_verified)  -> value string located in the cited passage
  * Fact (status=unverified)       -> extracted but not located verbatim (e.g. LLM output)
  * Calculation                    -> deterministic Python result over fact ids
  * Hypothesis                     -> a claim under test; carries status + evidence strength
  * Interpretation                 -> narrative text on a hypothesis; never a source of numbers
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DocType(str, Enum):
    annual_report = "annual_report"
    quarterly_results = "quarterly_results"
    investor_presentation = "investor_presentation"
    exchange_filing = "exchange_filing"
    announcement = "announcement"
    rating_report = "rating_report"
    industry = "industry"
    news = "news"
    other = "other"


class SourceTier(str, Enum):
    company = "company"          # issuer's own disclosure
    exchange = "exchange"        # NSE / BSE filing
    regulator = "regulator"      # CEA / MNRE / CERC / SEBI / PIB
    rating_agency = "rating_agency"
    media = "media"              # credible financial press
    unknown = "unknown"
    synthetic = "synthetic"      # demo mode only


TIER_WEIGHT = {
    SourceTier.company: 1.0,
    SourceTier.exchange: 1.0,
    SourceTier.regulator: 0.9,
    SourceTier.rating_agency: 0.8,
    SourceTier.media: 0.5,
    SourceTier.unknown: 0.3,
    SourceTier.synthetic: 1.0,
}


class FactType(str, Enum):
    reported = "reported"   # a disclosed outcome
    target = "target"       # a stated goal / guidance
    event = "event"         # a dated milestone or announcement


class FactStatus(str, Enum):
    source_verified = "source_verified"
    unverified = "unverified"
    rejected = "rejected"


class Scope(str, Enum):
    consolidated = "consolidated"
    standalone = "standalone"
    unknown = "unknown"


class HypothesisStatus(str, Enum):
    proposed = "proposed"
    supported = "supported"
    weakened = "weakened"
    rejected = "rejected"
    unresolved = "unresolved"
    insufficient_evidence = "insufficient_evidence"


class Strength(str, Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"
    insufficient = "insufficient"


class RelLabel(str, Enum):
    observed = "observed"          # directly stated in a source / extracted
    inferred = "inferred"          # produced by calculation or analysis
    contradictory = "contradictory"
    unverified = "unverified"


class Company(BaseModel):
    name: str
    nse: str = ""
    bse: str = ""
    aliases: list[str] = Field(default_factory=list)
    segment: str = ""
    website: str = ""
    eligible: bool = True
    resolution_note: str = ""


class Source(BaseModel):
    id: str = Field(default_factory=lambda: new_id("src"))
    run_id: str = ""
    url: str
    title: str = ""
    doc_type: DocType = DocType.other
    tier: SourceTier = SourceTier.unknown
    domain: str = ""
    published: Optional[str] = None  # ISO date if known
    retrieved_at: str = Field(default_factory=now_iso)
    fetch_status: str = "pending"    # pending | ok | failed | skipped
    error: str = ""
    n_pages: int = 0
    content_hash: str = ""
    query: str = ""                  # which search produced it
    purpose: str = "discovery"       # discovery | gap_fill | counterevidence | manual
    round: int = 1


class Fact(BaseModel):
    id: str = Field(default_factory=lambda: new_id("fct"))
    run_id: str = ""
    metric: str                       # canonical metric key, or "event"
    label: str = ""                   # raw label in the source
    value: Optional[float] = None     # normalised to canonical unit
    unit: str = ""                    # canonical unit
    raw_value: str = ""
    raw_unit: str = ""
    period: str = ""                  # FY2024 | Q2FY2025 | "" (point-in-time)
    period_end: Optional[str] = None  # ISO date
    period_inferred: bool = False     # period taken from document context, not the sentence
    fact_type: FactType = FactType.reported
    target_year: Optional[int] = None
    scope: Scope = Scope.unknown
    source_id: str = ""
    page: Optional[int] = None
    passage: str = ""
    extraction_method: str = "rule"   # rule | table | llm | manual | synthetic
    confidence: float = 0.5
    status: FactStatus = FactStatus.unverified
    event_category: str = ""          # commissioning | award | financing | rating | ...
    notes: str = ""


class Calculation(BaseModel):
    id: str = Field(default_factory=lambda: new_id("calc"))
    run_id: str = ""
    name: str
    formula: str
    input_fact_ids: list[str] = Field(default_factory=list)
    input_calc_ids: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    result: Optional[float] = None
    unit: str = ""
    period: str = ""
    status: str = "ok"                # ok | insufficient_data | incompatible | warning
    notes: str = ""
    module: str = ""


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: new_id("hyp"))
    run_id: str = ""
    module: str
    signal_key: str = ""              # stable key so later rounds revise rather than duplicate
    title: str
    statement: str
    direction: str = "risk"           # risk | opportunity | neutral
    status: HypothesisStatus = HypothesisStatus.proposed
    strength: Strength = Strength.insufficient
    score: float = 0.0
    supporting_fact_ids: list[str] = Field(default_factory=list)
    calc_ids: list[str] = Field(default_factory=list)
    counter_fact_ids: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    falsification: str = ""
    counter_queries: list[str] = Field(default_factory=list)
    counter_searched: bool = False    # True once counter-evidence queries have been run (or were impossible)
    checks: list[dict] = Field(default_factory=list)  # counter-check outcomes (name, effect, weight, fact_ids, note)
    params: dict[str, Any] = Field(default_factory=dict)
    interpretation: str = ""          # optional LLM/plain narrative, labelled as interpretation
    history: list[str] = Field(default_factory=list)
    round_created: int = 1
    round_updated: int = 1


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rel"))
    run_id: str = ""
    src_type: str
    src_id: str
    dst_type: str
    dst_id: str
    relation: str                     # extracted_from | input_to | supports | contradicts | linked_to | concerns
    label: RelLabel = RelLabel.observed
    note: str = ""


class ResearchEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt"))
    run_id: str = ""
    ts: str = Field(default_factory=now_iso)
    round: int = 0
    stage: str = ""
    level: str = "info"               # info | warning | error
    message: str = ""


class Run(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    company: Company
    mode: str = "live"                # live | demo | offline
    started_at: str = Field(default_factory=now_iso)
    finished_at: Optional[str] = None
    status: str = "running"           # running | completed | partial | failed
    settings: dict[str, Any] = Field(default_factory=dict)
    rounds_completed: int = 0
