"""LLM-assisted extraction with mandatory grounding.

The model proposes {metric, value_text, unit_text, period_text, quote}. A proposal is kept only if:
  * the quote occurs in the page text (whitespace-normalised), and
  * value_text occurs inside the quote.
Units and periods are then normalised by the same deterministic functions used by the rule extractor;
the model's own arithmetic or conversions are never used.
"""
from __future__ import annotations

import re
from typing import Optional

from ..metrics import METRICS, TARGET_BASE, metric_dimension, parse_number, unit_factor
from ..periods import parse_asof, parse_period, parse_target_year, period_end
from ..providers.llm import LLMProvider
from ..schema import Fact, FactStatus, FactType, Scope
from .documents import Document
from .rules import ExtractionContext, _scope_of

SYSTEM = (
    "You extract financial and operating facts from Indian energy-company disclosures. "
    "Only report numbers that literally appear in the text. Copy the quote verbatim (one sentence or table row). "
    "Do not convert units, do not compute anything, do not guess periods. If unsure, omit the item."
)

ALLOWED = sorted(list(METRICS) + list(TARGET_BASE))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def build_prompt(page_text: str) -> str:
    return (
        f"Allowed metric keys: {', '.join(ALLOWED)}.\n"
        "Return a JSON list of objects with keys: metric, value_text, unit_text, period_text, scope "
        "(consolidated|standalone|unknown), is_target (bool), target_year_text, quote.\n\n"
        f"TEXT:\n{page_text[:7000]}"
    )


def verify_and_build(item: dict, page_text: str, ctx: ExtractionContext, page_no: int) -> Optional[Fact]:
    metric = str(item.get("metric", ""))
    if metric not in ALLOWED:
        return None
    quote = str(item.get("quote", ""))
    vtxt = str(item.get("value_text", "")).strip()
    if not quote or not vtxt or _norm(quote) not in _norm(page_text) or vtxt not in quote:
        return None  # ungrounded -> discarded
    dim = metric_dimension(metric)
    fu = unit_factor(str(item.get("unit_text", "")), dim or "")
    if not fu:
        return None
    v = parse_number(vtxt)
    if v is None:
        return None
    ptxt = str(item.get("period_text", ""))
    period = (parse_period(ptxt) or parse_asof(ptxt)) if ptxt and ptxt in quote else None
    inferred = period is None
    period = period or parse_period(quote) or ctx.default_period or ""
    is_target = bool(item.get("is_target")) or metric in TARGET_BASE
    ty = parse_target_year(quote) if is_target else None
    if is_target and not ty:
        return None  # a target without a year in the text is not usable
    sc = str(item.get("scope", "unknown"))
    scope = Scope(sc) if sc in Scope._value2member_map_ and sc.lower() in quote.lower() else _scope_of(quote)
    return Fact(run_id=ctx.run_id, metric=metric, label=metric, value=v * fu[0], unit=fu[1], raw_value=vtxt,
                raw_unit=str(item.get("unit_text", "")), period=period, period_end=period_end(period),
                period_inferred=inferred, fact_type=FactType.target if is_target else FactType.reported,
                target_year=ty, scope=scope, source_id=ctx.source_id, page=page_no, passage=quote[:600],
                extraction_method="llm", confidence=0.55 if not inferred else 0.4,
                status=FactStatus.source_verified)


def extract_with_llm(doc: Document, ctx: ExtractionContext, llm: LLMProvider, max_pages: int = 12,
                     page_filter=None) -> tuple[list[Fact], int]:
    """Returns (verified facts, number of proposals discarded as ungrounded)."""
    if not llm.available:
        return [], 0
    facts, dropped = [], 0
    pages = [p for p in doc.pages if p.text.strip() and (page_filter is None or page_filter(p.text))][:max_pages]
    for p in pages:
        data = llm.complete_json(SYSTEM, build_prompt(p.text))
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            f = verify_and_build(item, p.text, ctx, p.number)
            if f:
                facts.append(f)
            else:
                dropped += 1
    return facts, dropped
