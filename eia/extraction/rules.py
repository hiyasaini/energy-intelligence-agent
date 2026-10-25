"""Deterministic, company-agnostic fact extraction.

Two passes per page:
  1. Narrative sentences: metric keyword + number + explicit unit (+ period / target cues).
  2. Tables: a header row with >=2 period columns, then rows whose label matches a metric.
     Money rows need an explicit unit (row label, header or page note such as "(₹ in crore)").
     Without a unit the row is skipped — units are never guessed.

Every fact keeps the exact passage it came from; the raw number string must occur in that passage,
which is what 'source_verified' means.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..metrics import METRICS, SOURCE_CAPACITY, TARGET_BASE, metric_dimension, parse_number, unit_factor
from ..periods import (header_periods as header_periods_in, parse_asof, parse_period, parse_target_year,
                       period_end, is_annual, is_quarter)
from ..schema import Fact, FactStatus, FactType, Scope
from .documents import Document

UNIT_RX = (r"million\s+tonnes\s+of\s+oil\s+equivalent|million\s+metric\s+tonnes|million\s+tonnes?|billion\s+tonnes|lakh\s+tonnes|"
           r"MMTOE|MTOE|MMTPA|MTPA|MMT|MT|BCM|billion\s+cubic\s+met(?:re|er)s|MMSCM|circuit\s+kilomet(?:re|er)s|circuit\s+km|cKm|MVA|GVA|"
           r"t\s?CO2e?\s?/\s?MWh|kg\s?CO2e?\s?/\s?kWh|g\s?CO2e?\s?/\s?kWh|lakh\s+crores?|lac\s+crores?|thousand\s+crores?|crores?|cr\.?|lakhs?|lacs?|million\s+units|billion\s+units|"
           r"million|mn|billion|bn|GWh|GWp|GWac|GW|MWp|MWac|MWdc|MW|MUs?|BU|TWh|MWh|kWh|per\s+cent|percent|%")
CURRENCY_RX = r"(?:₹|Rs\.?|INR|US\$|USD|\$)"
NUM_RX = r"\(?-?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?\)?|\(?-?\d+(?:\.\d+)?\)?"
NUM_UNIT = re.compile(
    rf"(?P<cur>{CURRENCY_RX})?\s*(?P<num>{NUM_RX})\+?\s*(?P<unit>{UNIT_RX})(?![A-Za-z])", re.I)

TARGET_CUES = re.compile(
    r"\b(target(s|ing|ed)?|aim(s|ing)?\s+(to|for|at)|plan(s|ning)?\s+to|envisag\w+|goal|guidance|ambition|"
    r"intend(s|ing)?\s+to|commit(s|ted|ment)?\s+to|aspir\w+|roadmap|vision\s+of|expects?\s+to\s+reach|to\s+reach|"
    r"plan(ned)?\s+(of|outlay)|outlay\s+of|guided|by\s+(the\s+end\s+of\s+)?(FY\s?'?\d{2,4}|20[2-6]\d)\b(?!\s*%))", re.I)
DELTA_CUES = re.compile(
    r"(\bby\b|\bincrease\s+of\b|\bdecrease\s+of\b|\bgrowth\s+of\b|\bdecline\s+of\b|\bup\b|\bdown\b|\bhigher\s+by\b|"
    r"\blower\s+by\b|\badditional\b|\banother\b|\bfurther\b|\badded\b|\baddition\s+of\b)\s*(?:of\s+)?(?:₹|Rs\.?|INR)?\s*$", re.I)
EVENT_CUES = [
    ("commissioning", re.compile(r"\b(commissioned|commissioning\s+of|achieved\s+COD|commercial\s+operation|operationali[sz]ed)\b", re.I)),
    ("award", re.compile(r"\b(won|awarded|secured|letter\s+of\s+award|\bLoA\b|bagged)\b", re.I)),
    ("ppa", re.compile(r"\b(signed\s+(an?\s+)?(PPA|power\s+purchase\s+agreement)|PPA\s+signed)\b", re.I)),
    ("financing", re.compile(r"\b(raised|QIP|qualified\s+institutional|rights\s+issue|bond\s+issue|NCDs?\b|green\s+bonds?|"
                             r"refinanc\w+|term\s+loan\s+sanction\w*)", re.I)),
    ("rating", re.compile(r"\b(credit\s+rating|rating\s+(upgrade|downgrade|reaffirm\w*)|upgraded|downgraded|outlook\s+(revised|changed))\b", re.I)),
    ("acquisition", re.compile(r"\b(acquired|acquisition\s+of|to\s+acquire)\b", re.I)),
    ("delay", re.compile(r"\b(delay(ed|s)?|postponed|slipp(ed|age)|behind\s+schedule)\b(?!\s+coker)", re.I)),
    ("curtailment", re.compile(r"\b(curtail(ed|ment)|grid\s+(constraint|congestion)|transmission\s+constraint)\b", re.I)),
]
DATE_RX = re.compile(
    r"\b(?:(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*,?\s+(20\d{2})|"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2}))\b", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

PAGE_UNIT_HINT = re.compile(
    rf"[\(\[]\s*(?:all\s+)?(?:amounts?\s+|figures?\s+)?(?:are\s+)?(?:in\s+)?{CURRENCY_RX}?\s*(?:in\s+)?"
    rf"(?P<unit>lakhs?|lacs?|crores?|cr\.?|million|mn|billion)\s*[\)\]]", re.I)
PAGE_UNIT_HINT2 = re.compile(rf"{CURRENCY_RX}\s*in\s+(?P<unit>lakhs?|lacs?|crores?|cr|million|mn|billion)\b", re.I)
# "Figures in Rs. Crores", "Amounts in INR lakhs", "Reporting unit: Lakhs (INR)", "(In ₹ Crore)"
PAGE_UNIT_HINT3 = re.compile(
    rf"\b(?:figures|amounts?|all\s+amounts?|reporting\s+unit|unit|currency)\s*(?:are\s+)?(?:in|:)\s*(?:{CURRENCY_RX}\s*)?"
    rf"(?:in\s+)?(?P<unit>lakhs?|lacs?|crores?|cr\.?|million|mn|billion)\b", re.I)
PAGE_UNIT_HINT4 = re.compile(rf"\b(?P<unit>lakhs?|lacs?|crores?)\s*\(\s*(?:INR|Rs\.?|₹)\s*\)", re.I)
ROW_NUM = re.compile(rf"(?<![\w.])(?:{NUM_RX}|-)(?![\w.])")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z₹(])|;\s+|\n{2,}|•|\n(?=[A-Z•\-–])")


@dataclass
class ExtractionContext:
    run_id: str
    source_id: str
    default_period: Optional[str] = None
    is_synthetic: bool = False
    scope_hint: str = ""      # e.g. the document URL or title; "/consolidated/" there sets the default scope
    company_words: tuple = ()  # the company's own names (registry name, aliases, symbol): mark "own" statements


_SCOPE_LINK = re.compile(r"\bview\s+(?:standalone|consolidated)\b|\b(?:standalone|consolidated)\s+view\b", re.I)
_SCOPE_LABEL = re.compile(r"\b(consolidated|standalone)\s+(?:figures|financials?|results|statements?|basis)\b", re.I)


def _scope_of(text: str) -> Scope:
    t = _SCOPE_LINK.sub(" ", text).lower()        # link text to the other view says nothing about this one
    lab = {m.group(1).lower() for m in _SCOPE_LABEL.finditer(t)}
    if len(lab) == 1:
        return Scope.consolidated if "consolidated" in lab else Scope.standalone
    c, s = "consolidated" in t, "standalone" in t
    if c and not s:
        return Scope.consolidated
    if s and not c:
        return Scope.standalone
    return Scope.unknown


def _page_unit(text: str) -> Optional[str]:
    m = (PAGE_UNIT_HINT.search(text) or PAGE_UNIT_HINT2.search(text) or PAGE_UNIT_HINT3.search(text)
         or PAGE_UNIT_HINT4.search(text))
    return m.group("unit") if m else None


def document_default_period(doc: Document) -> Optional[str]:
    """Period that the document as a whole reports on (from title / first pages)."""
    head = (doc.title or "") + "\n" + "\n".join(p.text for p in doc.pages[:2])[:6000]
    return parse_period(head) or parse_asof(head)


def _event_date(text: str) -> Optional[str]:
    m = DATE_RX.search(text)
    if not m:
        return None
    try:
        if m.group(1):
            d, mo, y = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3))
        else:
            mo, d, y = MONTHS[m.group(4)[:3].lower()], int(m.group(5)), int(m.group(6))
        from datetime import date
        return date(y, mo, d).isoformat()
    except Exception:
        return None


NATIONAL_CUES = re.compile(r"\bIndia(?:'s|’s)?\b|\bcountry(?:'s|’s)?\b|\bnation(?:al|'s|’s)?\b|\bgovernment\b|\bGoI\b|"
                          r"\bministry\b|\bMoP\b|\bMNRE\b|\bglobal(?:ly)?\b|\bworld(?:wide)?\b|\bsector\b", re.I)
OWN_CUES = re.compile(r"\b(?:our|its|company(?:'s|’s)|group(?:'s|’s))\b|\bwe\s+(?:aim|plan|target|intend|expect|will)", re.I)


PHYSICAL_DIMS = {"power", "energy", "mass", "oil_eq", "gas_vol", "length", "apparent_power"}


PHYS_INCREMENT_AFTER = re.compile(r"^[^.;]{0,60}?\b(added|addition|additions|was\s+commissioned|were\s+commissioned)\b", re.I)
PHYS_INCREMENT_BEFORE = re.compile(r"\b(additions?|added|adding|increase[ds]?\s+by|grew\s+by|rose\s+by)\s*(of\s+)?\(?\s*$", re.I)
PHYS_TOTAL_BEFORE = re.compile(r"\b(total|cumulative|aggregate|taking\s+the|operational|operating|installed)\b[^.;]{0,40}$", re.I)
PHYS_RATIO = re.compile(r"intensity|per\s+(unit|kwh|mwh|mw|tonne)|/\s*(total|kwh|mwh|mw)|saving|saved|save\b|consum", re.I)
CAPACITY_KEYS = {"installed_capacity_mw", "renewable_capacity_mw"}


OWN_STRONG = re.compile(r"\b(our|we|us|the\s+company|your\s+company|the\s+corporation|your\s+corporation|the\s+group)\b", re.I)


def _physical_ok(sentence: str, nm, key: str, mdef, ctx, kw_end: int = 0) -> bool:
    """Generic tests for capacity, generation and production numbers written in prose."""
    before, after = sentence[max(0, nm.start() - 80):nm.start()], sentence[nm.end():nm.end() + 70]
    between = sentence[max(kw_end, nm.start() - 40):nm.start()] if kw_end < nm.start() else sentence[max(0, nm.start() - 40):nm.start()]
    own_words = [w for w in getattr(ctx, "company_words", ()) if w]
    own = bool(OWN_STRONG.search(sentence)) or any(re.search(rf"\b{re.escape(w)}\b", sentence, re.I) for w in own_words)
    if not is_target_sentence_number(sentence, nm) and NATIONAL_CUES.search(sentence) and not own:
        return False   # a country, global or sector statistic quoted for context
    if PHYS_RATIO.search(before[-60:]) or PHYS_RATIO.search(after[:25]):
        return False   # a ratio, intensity or saving, not a level
    if mdef.kind == "stock" and not is_target_sentence_number(sentence, nm):
        if PHYS_INCREMENT_BEFORE.search(before) or (PHYS_INCREMENT_AFTER.search(after) and not PHYS_TOTAL_BEFORE.search(before)):
            return False   # capacity added in the year, not the capacity level
        if key in CAPACITY_KEYS and NOT_OPERATING.search(between + " " + after[:60]) and \
                not PHYS_TOTAL_BEFORE.search(before):
            return False   # pipeline, locked-in or under-construction capacity
        if key in CAPACITY_KEYS and re.search(r"locked[\s-]*in|including\s+under|portfolio\s+of", before[-50:] + after[:50], re.I):
            return False
    return True


def is_target_sentence_number(sentence: str, nm) -> bool:
    """Targets have their own national-goal filter further down."""
    return bool(TARGET_CUES.search(sentence)) and parse_target_year(sentence) is not None


def _target_metric(base: str, sentence: str) -> Optional[str]:
    if base in ("installed_capacity_mw", "capacity_under_construction_mw"):
        return "renewable_target_mw" if re.search(r"renewable|\bRE\b|green|clean|solar|wind", sentence, re.I) \
            else "capacity_target_mw"
    if base == "renewable_capacity_mw":
        return "renewable_target_mw"
    for t, b in TARGET_BASE.items():
        if b == base:
            return t
    return None


def _confidence(base: float, period_inferred: bool, scope: Scope) -> float:
    c = base - (0.15 if period_inferred else 0) - (0.05 if scope == Scope.unknown else 0)
    return round(max(0.1, min(0.95, c)), 2)


def _sentences(text: str) -> list[str]:
    parts = [re.sub(r"\s+", " ", s).strip() for s in SENT_SPLIT.split(text)]
    return [p for p in parts if 15 <= len(p) <= 700]


NOT_OPERATING = re.compile(r"under[\s-]*(construction|development|implementation|execution|installation)|pipeline|"
                           r"planned|proposed|upcoming|target|to\s+be\s+commissioned|awarded|won|commissioned|commissioning|added|"
                           r"addition|acquired|acquisition|signed|PPA|order", re.I)
FUTURE_CUE = re.compile(r"\b(between|by|till|until|scheduled|expected|targeted|planned|over|through|from)\b", re.I)


def _nearest_period(sentence: str, start: int, end: int) -> Optional[str]:
    after = sentence[end:end + 35]
    p = parse_period(after) or parse_asof(after)
    if p:
        # "... 3,100 MW, scheduled between FY2026 and FY2028" -> a future window, not the reporting period
        m = re.search(r"(FY|Q[1-4]|20\d{2}|as\s+(on|of|at))", after, re.I)
        if not (m and FUTURE_CUE.search(after[:m.start()])):
            return p
    before = sentence[max(0, start - 30):start]
    p = parse_period(before) or parse_asof(before)
    if p and is_annual(p):
        # the window may have cut "Q1 " off "Q1 FY 27": a quarter for the same year just before wins
        wide = parse_period(sentence[max(0, start - 40):start])
        if wide and is_quarter(wide) and wide.endswith(p[2:]):
            return wide
    return p


BEFORE_CONNECTOR = re.compile(r"^\s*(of|in|is|are|was|were)?\s*(\w+\s+){0,2}(of\s+)?$", re.I)


def _keyword_spans(sentence: str) -> list[tuple[int, int, str, str]]:
    """Non-overlapping (start, end, metric_key, text) keyword hits; registry order = specificity."""
    spans: list[tuple[int, int, str, str]] = []
    for mdef in METRICS.values():
        for p in mdef.patterns:
            for m in p.finditer(sentence):
                if any(not (m.end() <= s or m.start() >= e) for s, e, _, _ in spans):
                    continue
                spans.append((m.start(), m.end(), mdef.key, m.group(0)))
    return sorted(spans)


def extract_from_sentence(sentence: str, ctx: ExtractionContext, page_no: int, page_scope: Scope) -> list[Fact]:
    facts: list[Fact] = []
    scope = _scope_of(sentence)
    if scope == Scope.unknown:
        scope = page_scope
    is_target = bool(TARGET_CUES.search(sentence))
    target_year = parse_target_year(sentence) if is_target else None
    sent_asof = parse_asof(sentence)
    sent_period = parse_period(sentence) or sent_asof
    kws = _keyword_spans(sentence)
    if not kws:
        return facts
    used_kw: dict[int, int] = {}  # keyword index -> facts taken

    for nm in NUM_UNIT.finditer(sentence):
        unit_txt = ((nm.group("cur") or "") + " " + nm.group("unit")).strip()
        # candidate keyword: nearest preceding within 140 chars, else immediately following ("50 GW of RE capacity")
        best = None
        for i, (s, e, key, _) in enumerate(kws):
            dim = METRICS[key].dimension
            if not unit_factor(unit_txt, dim):
                continue
            if e <= nm.start() and nm.start() - e <= 140:
                # ensure no other keyword sits between this keyword and the number
                if any(e <= s2 < nm.start() and unit_factor(unit_txt, METRICS[k2].dimension)
                       for s2, _, k2, _ in kws if s2 != s):
                    continue
                best = i
            elif s >= nm.end() and s - nm.end() <= 30 and BEFORE_CONNECTOR.match(sentence[nm.end():s]):
                # "60 GW of renewable capacity": a keyword right after the number binds to it, unless the
                # keyword before it has no number yet
                if best is None or used_kw.get(best):
                    best = i
                break
        if best is None:
            continue
        s, e, key, kw_text = kws[best]
        mdef = METRICS[key]
        if key in SOURCE_CAPACITY and NOT_OPERATING.search(sentence):
            continue  # pipeline / planned capacity is not operating capacity
        if key == "refinery_throughput_mt" and re.search(r"pipeline", sentence[max(0, s - 40):e + 40], re.I):
            continue  # pipeline throughput (oil moved through pipelines) is not refinery throughput
        if mdef.dimension in PHYSICAL_DIMS and not _physical_ok(sentence, nm, key, mdef, ctx, e):
            continue
        if mdef.dimension == "money" and RATIO_LABEL.search(sentence[max(0, s - 25):e + 15]):
            continue
        if e <= nm.start():
            prefix = sentence[max(e, nm.start() - 30):nm.start()]
            if DELTA_CUES.search(prefix):
                continue  # change amount, not a level
        fu = unit_factor(unit_txt, mdef.dimension)
        raw_num = nm.group("num")
        val = parse_number(raw_num)
        if val is None or fu is None:
            continue
        own_period = _nearest_period(sentence, nm.start(), nm.end())
        if mdef.kind == "stock" and sent_asof:
            own_period = sent_asof  # point-in-time balances: an explicit "as on <date>" wins
        if used_kw.get(best, 0) and not own_period:
            continue  # later numbers for the same keyword need their own period
        period = own_period or sent_period or ctx.default_period or ""
        inferred = not (own_period or sent_period)
        ftype, metric, tyear = FactType.reported, mdef.key, None
        if is_target and target_year and NATIONAL_CUES.search(sentence[max(0, nm.start() - 120):nm.start()]) and \
                not OWN_CUES.search(sentence[max(0, nm.start() - 60):nm.start()]):
            continue  # a country / government goal quoted in the report, not the company's own target
        if is_target and target_year:
            # renewable vs total is decided by the words around THIS number, not anywhere in the sentence
            tm = _target_metric(mdef.key, sentence[max(0, min(s, nm.start()) - 40):max(e, nm.end())])
            if tm:
                metric, ftype, tyear = tm, FactType.target, target_year
                period, inferred = (sent_period or ctx.default_period or ""), not sent_period
                if sent_period and parse_target_year(sentence) and period_end(sent_period) and \
                        int(period_end(sent_period)[:4]) >= target_year:
                    period, inferred = ctx.default_period or "", True  # sentence period was the target year
        used_kw[best] = used_kw.get(best, 0) + 1
        facts.append(Fact(
            run_id=ctx.run_id, metric=metric, label=kw_text, value=val * fu[0], unit=fu[1],
            raw_value=raw_num, raw_unit=unit_txt, period=period, period_end=period_end(period),
            period_inferred=inferred, fact_type=ftype, target_year=tyear, scope=scope,
            source_id=ctx.source_id, page=page_no, passage=sentence,
            extraction_method="synthetic" if ctx.is_synthetic else "rule",
            confidence=_confidence(0.65, inferred, scope),
            status=FactStatus.source_verified if raw_num in sentence else FactStatus.unverified))
    return facts


# a delay only counts when it is about a project, and stated as fact (not a risk-factor "could be delayed")
DELAY_SUBJECT = re.compile(r"\b(project|commission\w*|COD|construction|unit|plant|block|field|mine|well|line|substation|"
                           r"refinery|execution|schedule|completion|land|clearance|capacity)\b", re.I)
DELAY_NOISE = re.compile(r"\b(may|might|could|can|would|risks?|potential(ly)?|in\s+case\s+of|if|whether|"
                         r"without\s+delay|delayed\s+payment|late\s+payment|surcharge|interest\s+on|share\s+transfer|"
                         r"temporary\s+delay|avoid\w*|minimi[sz]\w*|mitigat\w*|prevent\w*|reduc\w+|"
                         # accounting-policy text: pension curtailments, capitalisation rules, recognition
                         r"plan\s+amendment|settlement|service\s+cost|actuarial|gratuity|pension|capitalis\w*|"
                         r"capitaliz\w*|recogni[sz]\w*|accounting\s+polic\w*)\b", re.I)


def extract_events(sentence: str, ctx: ExtractionContext, page_no: int, page_scope: Scope) -> list[Fact]:
    out = []
    for cat, rx in EVENT_CUES:
        m = rx.search(sentence)
        if not m:
            continue
        if cat in ("delay", "curtailment") and (DELAY_NOISE.search(sentence) or
                                                (cat == "delay" and not DELAY_SUBJECT.search(sentence))):
            continue
        cap = None
        raw_v, raw_u = "", ""
        for nm in NUM_UNIT.finditer(sentence):
            fu = unit_factor(nm.group("unit"), "power")
            if fu:
                cap = parse_number(nm.group("num"))
                if cap is not None:
                    cap *= fu[0]
                    raw_v, raw_u = nm.group("num"), nm.group("unit")
                break
        d = _event_date(sentence)
        per = parse_period(sentence) or parse_asof(sentence)
        if not d and not per and not ctx.default_period:
            continue  # undated events are not placed on the timeline
        out.append(Fact(
            run_id=ctx.run_id, metric="event", label=m.group(0), value=cap, unit="MW" if cap is not None else "",
            raw_value=raw_v, raw_unit=raw_u, period=per or ctx.default_period or "",
            period_end=d or period_end(per or ctx.default_period or ""), period_inferred=not (d or per),
            fact_type=FactType.event, scope=page_scope, source_id=ctx.source_id, page=page_no, passage=sentence,
            extraction_method="synthetic" if ctx.is_synthetic else "rule", event_category=cat,
            confidence=0.6 if d else 0.45, status=FactStatus.source_verified))
        break
    return out


_PERIOD_TOKEN = re.compile(
    r"\b(Q[1-4]\s?[- ]?\s?FY\s?'?\d{2,4}|FY\s?'?\d{2,4}(\s?[-–/]\s?\d{2,4})?|20\d{2}\s?[-–/]\s?\d{2,4}|"
    r"(quarter|year|months)\s+ended\s+\S+\s+\S+,?\s+\d{4})\b", re.I)


_MONTH_WORD = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b", re.I)
_PERIODISH = re.compile(r"\b(FY\s?'?\d{2,4}|Q[1-4]\b|20\d{2}|\d{2}\s?[-–]\s?\d{2}|(Jan|Mar|Jun|Sep|Dec)[a-z]*[\s'-]*\d{2,4})", re.I)
# rows whose label is a ratio / per-share / percentage measure must never be read as an amount
RATIO_LABEL = re.compile(r"\s/\s|\bratio\b|\bto\s+(equity|ebitda|net\s*worth)|\bcoverage\b|\bper\s+share\b|\bmargin\b|"
                         r"\breturn\s+on\b|\b(RoE|RoCE|EPS)\b|\bdays\b|\btimes\b|\byield\b", re.I)


def _header_like(line: str) -> bool:
    stripped = _PERIODISH.sub(" ", _MONTH_WORD.sub(" ", _PERIOD_TOKEN.sub(" ", line)))
    stripped = re.sub(r"%\s*(growth|change|chg)|\b(yoy|qoq)\b", " ", stripped, flags=re.I)
    if NUM_UNIT.search(stripped):
        return False
    words = re.findall(r"[A-Za-z]{2,}", stripped)
    return len(words) <= 8


def extract_tables(text: str, ctx: ExtractionContext, page_no: int, page_scope: Scope) -> list[Fact]:
    facts: list[Fact] = []
    lines = text.splitlines()
    page_unit = _page_unit(text)
    header_periods: list[Optional[str]] = []
    header_line = ""
    header_unit: Optional[str] = None
    rows_since_header = 0
    scope = page_scope
    for i, line in enumerate(lines):
        context = "\n".join(lines[max(0, i - 2):i])
        periods = header_periods_in(line, context)
        labelled = [p for p in periods if p]
        single = len(periods) == 1 and labelled and len(ROW_NUM.findall(_PERIOD_TOKEN.sub(" ", _date_free(line)))) == 0
        if not (labelled and (len(periods) >= 2 or single)) and _header_like(line) and \
                len(_PERIODISH.findall(line)) >= 2 and not ROW_NUM.search(_PERIODISH.sub(" ", line)):
            header_periods = []  # a header we cannot read: stop attributing rows to the previous header
            continue
        if labelled and (len(periods) >= 2 or single) and _header_like(line):
            header_periods, header_line, rows_since_header = periods, line, 0
            header_unit = _page_unit(line)
            # scope from header or lines just above it
            ctx_text = "\n".join(lines[max(0, i - 4):i + 1])
            sc = _scope_of(ctx_text)
            scope = sc if sc != Scope.unknown else page_scope
            continue
        if not header_periods:
            continue
        rows_since_header += 1
        if rows_since_header > 60:
            header_periods = []
            continue
        nums = [m for m in ROW_NUM.finditer(line)]
        if len(nums) < len(header_periods) or (len(header_periods) == 1 and len(nums) != 1):
            continue
        label = line[:nums[0].start()].strip(" :.-–+")
        if not label or len(label) > 120 or not re.search(r"[A-Za-z]{3}", label):
            continue
        tail = line[nums[0].start():]
        if re.search(r"[A-Za-z]{2,}", ROW_NUM.sub(" ", tail)):
            continue  # prose, not a numeric table row
        mdef = next((m for m in METRICS.values() if any(p.search(label) for p in m.patterns)), None)
        if not mdef:
            continue
        if mdef.dimension in ("money", "power", "energy") and RATIO_LABEL.search(label):
            continue  # "Net Debt / EBITDA", "Debt to equity", "Interest coverage" are ratios, not amounts
        # an explicit non-matching unit in the row label ("(times)", "(₹)" per share, "(days)") vetoes the row,
        # even if the page carries a money unit note
        veto = ROW_UNIT_ANY.search(label)
        if veto and not unit_factor(veto.group(1), mdef.dimension):
            continue
        # unit: row label > header line > page note
        row_unit_m = re.search(rf"\(\s*{CURRENCY_RX}?\s*(?:in\s+)?({UNIT_RX})\s*\)", label, re.I)
        unit_txt = row_unit_m.group(1) if row_unit_m else (header_unit or (page_unit if mdef.dimension == "money" else None))
        if unit_txt is None and mdef.dimension in ("percent",):
            unit_txt = "%"
        if unit_txt is None:
            continue  # never guess units
        fu = unit_factor(unit_txt, mdef.dimension)
        if not fu:
            continue
        values = nums
        # drop a leading note-reference column (small integer) when there is one extra number
        if len(values) == len(header_periods) + 1 and re.fullmatch(r"\d{1,2}", values[0].group(0)):
            values = values[1:]
        values = values[:len(header_periods)]
        passage = (header_line.strip() + "\n" + line.strip())[:600]
        for per, nm in zip(header_periods, values):
            if not per:
                continue  # column without a canonical period (nine months, ambiguous date)
            raw = nm.group(0)
            v = parse_number(raw) if raw != "-" else None
            if v is None:
                continue
            facts.append(Fact(
                run_id=ctx.run_id, metric=mdef.key, label=label[:80], value=v * fu[0], unit=fu[1], raw_value=raw,
                raw_unit=unit_txt, period=per, period_end=period_end(per), period_inferred=False,
                fact_type=FactType.reported, scope=scope, source_id=ctx.source_id, page=page_no, passage=passage,
                extraction_method="synthetic" if ctx.is_synthetic else "table",
                confidence=_confidence(0.75, False, scope),
                status=FactStatus.source_verified if raw in passage else FactStatus.unverified))
    return facts


ROW_UNIT_ANY = re.compile(rf"\(\s*(?:in\s+)?((?:{CURRENCY_RX}\s*)?(?:{UNIT_RX})|times|x|days|{CURRENCY_RX}|"
                          rf"per\s+share|ratio)\s*\)", re.I)
_DATE_TOKEN = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]20\d{2}\b|\b\d{1,2}(st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+20\d{2}\b")


def _date_free(line: str) -> str:
    return _DATE_TOKEN.sub(" ", line)


def combine_borrowings(facts: list[Fact]) -> list[Fact]:
    """Gross debt = non-current + current borrowings when a source reports only the components for a period.
    Deterministic, documented, and verifiable: both raw numbers are kept in the passage."""
    out = []
    have_gross = {(f.source_id, f.period, f.scope) for f in facts if f.metric == "gross_debt_cr"}
    nc = {(f.source_id, f.period, f.scope): f for f in facts if f.metric == "borrowings_noncurrent_cr"}
    cu = {(f.source_id, f.period, f.scope): f for f in facts if f.metric == "borrowings_current_cr"}
    for k, a in nc.items():
        b = cu.get(k)
        if not b or k in have_gross or a.unit != b.unit:
            continue
        passage = (a.passage + "\n" + b.passage.splitlines()[-1])[:700]
        out.append(Fact(
            run_id=a.run_id, metric="gross_debt_cr", label="non-current + current borrowings", value=a.value + b.value,
            unit=a.unit, raw_value=f"{a.raw_value} + {b.raw_value}", raw_unit=a.raw_unit, period=a.period,
            period_end=a.period_end, period_inferred=a.period_inferred or b.period_inferred, scope=a.scope,
            source_id=a.source_id, page=a.page, passage=passage, extraction_method="table_sum",
            confidence=min(a.confidence, b.confidence),
            status=FactStatus.source_verified if a.raw_value in passage and b.raw_value in passage
            else FactStatus.unverified,
            notes=f"Sum of reported components {a.id} + {b.id}."))
    return out


def extract_document(doc: Document, ctx: ExtractionContext) -> list[Fact]:
    if ctx.default_period is None:
        ctx.default_period = document_default_period(doc)
    out: list[Fact] = []
    doc_scope = _scope_of(ctx.scope_hint.replace("/", " ")) if ctx.scope_hint else Scope.unknown
    for page in doc.pages:
        if not page.text.strip():
            continue
        page_scope = _scope_of(page.text[:600])
        if page_scope == Scope.unknown:
            page_scope = doc_scope
        out.extend(extract_tables(page.text, ctx, page.number, page_scope))
        for s in _sentences(page.text):
            if len(ROW_NUM.findall(s)) > 8 or len(re.findall(r"\s{3,}\(?-?[\d,.]+%?\)?", s)) >= 2:
                continue  # table row (columns separated by wide gaps); handled by the table pass
            out.extend(extract_from_sentence(s, ctx, page.number, page_scope))
            out.extend(extract_events(s, ctx, page.number, page_scope))
    out = dedupe(out)
    return out + combine_borrowings(out)


def dedupe(facts: list[Fact]) -> list[Fact]:
    seen, out = set(), []
    for f in facts:
        key = (f.metric, f.period, f.fact_type.value, f.target_year, round(f.value, 4) if f.value is not None else None,
               f.source_id, f.scope.value, f.event_category, f.passage[:60] if f.metric == "event" else "")
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out
