"""Discovery brief: the eight elements the brief asks for, assembled from one run's evidence.

  1. The Discovery        one sentence (the finding's own statement, which every number in it comes from)
  2. Why it matters       3-5 bullets from a fixed, finding-type template (no new numbers are introduced)
  3. Evidence             supporting facts grouped by source document, with links and pages
  4. Timeline             the dated facts behind the finding, in order, and when the change first shows
  5. Numbers              only the calculations attached to the finding
  6. Counterargument      the strongest opposing check, else the strongest alternative explanation
  7. Falsification        the finding's own condition
  8. Evidence strength    grade plus the reasons for it

Selection prefers findings that survived the counter-evidence search, are backed by more than one source
document and point to a risk or opportunity (not a neutral observation). Everything is deterministic.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from .db import Store
from .modules.base import fmt
from .periods import period_sort_key
from .schema import Hypothesis, HypothesisStatus
from .verification import status_label

STATUS_RANK = {HypothesisStatus.supported: 0, HypothesisStatus.unresolved: 1, HypothesisStatus.weakened: 2,
               HypothesisStatus.proposed: 3, HypothesisStatus.insufficient_evidence: 5,
               HypothesisStatus.rejected: 6}
STRENGTH_RANK = {"strong": 0, "moderate": 1, "weak": 2, "insufficient": 3}

# "Why it matters" templates, keyed by finding type (module:type). Wording only: never adds numbers.
WHY = {
    "promise_reality:pace": [
        "The stated target is the yardstick investors and lenders use; missing it usually means guidance resets.",
        "Delivering faster than ever before needs land, transmission, equipment and funding all at once.",
        "If the pace does not change, the gap compounds every year the target stays unchanged.",
        "Capacity that slips also delays the revenue and cash flow the plan assumes.",
    ],
    "promise_reality:capex_step_up": [
        "A step-up in spending has to be funded by operating cash, new debt or new equity.",
        "Large programmes stretch project execution and supplier capacity at the same time.",
        "Returns arrive years after the spending, so leverage usually rises first.",
    ],
    "promise_reality:revision": [
        "Different numbers for the same target suggest a revision, or a group vs listed-company scope difference.",
        "Readers comparing documents can be anchored to the wrong figure.",
        "It is worth confirming which number management is accountable for.",
    ],
    "green_growth:lag": [
        "Capacity that does not turn into output or revenue earns nothing on the capital spent.",
        "It can point to late commissioning, curtailment, weak resource years or transmission constraints.",
        "Returns on new assets look worse until output catches up.",
    ],
    "green_growth:price_led": [
        "Growth from price, tariff or mix is harder to repeat than growth from selling more.",
        "If prices or regulated tariffs normalise, revenue growth slows even with steady volumes.",
        "A headline growth figure can hide flat underlying demand or output.",
        "Checking peers separates a company story from a sector-wide price cycle.",
    ],
    "green_growth:realisation_down": [
        "Selling more at lower prices squeezes margins unless costs fall as fast.",
        "Falling realisations can reflect a weaker customer mix, discounts or regulated tariff cuts.",
        "Volume-led growth that does not lift revenue adds work without adding earnings.",
    ],
    "capital_cash:leverage": [
        "High debt relative to earnings leaves less room if earnings dip or rates rise.",
        "Lenders and rating agencies watch this ratio closely; breaches can raise borrowing costs.",
        "It limits funding for the growth plan without new equity.",
    ],
    "capital_cash:coverage": [
        "A thin cushion between earnings and interest means a small earnings dip can strain debt service.",
        "Refinancing at higher rates would narrow the cushion further.",
        "Coverage is one of the first ratios lenders test.",
    ],
    "capital_cash:conversion": [
        "Profits that do not turn into cash cannot fund capex or repay debt.",
        "Weak conversion often traces to rising receivables or working capital.",
        "Reported earnings may overstate the cash the business generates.",
    ],
    "capital_cash:fcf_negative": [
        "Repeated negative free cash flow means growth is funded by borrowing or equity.",
        "It makes the company dependent on capital markets staying open.",
        "Debt tends to keep rising until projects start paying back.",
    ],
    "capital_cash:debt_outpaces_ebitda": [
        "Debt rising faster than earnings pushes leverage up year after year.",
        "Each new project must earn more just to keep the balance sheet steady.",
        "It narrows the margin for error if projects are delayed.",
    ],
    "capital_cash:finance_cost_outpaces_revenue": [
        "Interest costs growing faster than revenue eat into profits directly.",
        "It can reflect more borrowing, higher rates, or interest no longer capitalised on finished projects.",
        "Profit growth will lag revenue growth while this lasts.",
    ],
    "hidden_risk:receivables": [
        "Rising receivable days tie up cash in unpaid bills.",
        "In Indian power, slow-paying distribution companies are a long-running credit risk.",
        "Reported revenue can look healthy while cash collection weakens.",
    ],
    "hidden_risk:composite": [
        "Several independent warning signs appearing together deserve more attention than any one alone.",
        "They point to pressure across growth, funding and cash at the same time.",
        "Co-occurrence does not prove a shared cause, so each signal is shown with its own evidence.",
    ],
    "hidden_connections:event_gap": [
        "Announcements that do not show up in reported figures can signal delays or scope differences.",
        "It tests whether press releases and filings tell the same story.",
        "Investors often price in announcements before they become operating results.",
    ],
    "hidden_connections:corr": [
        "Two metrics moving together suggests a dependency worth understanding.",
        "This is an association over a small sample, not proof of cause and effect.",
        "It helps decide which metric to watch as an early signal for the other.",
    ],
    "early_warning:quarter": [
        "A sharp quarterly move is often the first visible sign of a change in trend.",
        "It shows up in exchange filings before the annual report confirms it.",
        "One quarter can be noise, so the next quarter is the real test.",
    ],
    "early_warning:margin": [
        "Falling margins mean each rupee of revenue earns less.",
        "It can reflect fuel or input costs, tariff pressure or a change in business mix.",
        "Margin trends often move before profit headlines do.",
    ],
    "early_warning": [
        "A reversal or sharp slowdown can be the first sign of a turning point.",
        "It shows up in the numbers before it shows up in management commentary.",
        "The next reporting period will show whether it is a blip or a trend.",
    ],
}
GENERIC_WHY = [
    "It is visible only when several disclosures are read together, not in any single document.",
    "It affects how sustainable the company's reported growth and funding plans are.",
    "It can be monitored with the falsification condition below as new filings arrive.",
]


def _why(h: Hypothesis) -> list[str]:
    parts = h.signal_key.split(":")
    for k in (":".join(parts[:2]), parts[0]):
        if k in WHY:
            return WHY[k][:5]
    return GENERIC_WHY


# Finding types that only appear when documents are read together (what a normal dashboard would miss).
NON_OBVIOUS = {"promise_reality:pace", "promise_reality:capex_step_up", "green_growth:price_led",
               "green_growth:realisation_down", "green_growth:lag", "hidden_connections:event_gap",
               "hidden_risk:composite", "hidden_risk:receivables", "capital_cash:debt_outpaces_ebitda",
               "capital_cash:finance_cost_outpaces_revenue"}


def is_non_obvious(h: Hypothesis) -> bool:
    return ":".join(h.signal_key.split(":")[:2]) in NON_OBVIOUS


def _novelty(h: Hypothesis) -> int:
    if h.signal_key.startswith("hidden_risk:composite"):
        return 1          # a summary of other findings: shown after the specific ones it summarises
    return 0 if is_non_obvious(h) else 2


def _rank(h: Hypothesis, n_sources: int) -> tuple:
    """The headline must be a triangulated finding: evidence from two or more documents comes first (the brief:
    "findings should not rest on a single document"), then risk/opportunity before neutral observations, then
    findings that are not weakened, then non-obvious finding types, then status and evidence grade."""
    weak = h.strength.value == "insufficient" or h.status.value == "insufficient_evidence"
    standing = 0 if h.status in (HypothesisStatus.supported, HypothesisStatus.unresolved) else 1
    return (1 if weak else 0, 0 if n_sources >= 2 else 1, 0 if h.direction != "neutral" else 1, standing,
            _novelty(h), STATUS_RANK.get(h.status, 4), STRENGTH_RANK.get(h.strength.value, 3), -h.score)


def _strength_reasons(h: Hypothesis, sup: list[dict], sources: list, checks: list[dict]) -> list[str]:
    tiers = sorted({s.tier.value for s in sources})
    verified = sum(1 for r in sup if r["status"] == "source_verified")
    opp = [c for c in checks if c.get("effect") == "opposes"]
    out = [f"{len(sup)} supporting fact(s) from {len(sources)} source document(s) ({', '.join(tiers) or 'unknown'} tier).",
           f"{verified} of {len(sup)} facts were found word for word in the cited passage." if sup else
           "No supporting facts are attached."]
    w = sum(float(c.get("weight", 0)) for c in opp)
    if not checks:
        out.append("No counter-checks apply to this finding type.")
    elif not opp:
        out.append(f"{len(checks)} counter-check(s) run; none found opposing evidence.")
    else:
        out.append(f"{len(checks)} counter-check(s) run; {len(opp)} found some opposing evidence"
                   + (" (not enough to weaken the finding; it is stated as the counterargument)." if w < 0.4 else "."))
    out.append("The counter-evidence search was run." if h.counter_searched else
               "The counter-evidence search has not run yet for this finding.")
    lims = [x for x in h.limitations if not (len(sources) >= 2 and "single source" in x.lower())]
    out += [f"Limitation: {x}" for x in lims[:2]]
    return out


def _counterargument(h: Hypothesis, checks: list[dict]) -> str:
    opp = sorted([c for c in checks if c.get("effect") == "opposes"], key=lambda c: -float(c.get("weight", 0)))
    if opp and opp[0].get("note"):
        return opp[0]["note"]
    specific = [c for c in h.counterarguments if not c.startswith("No opposing evidence")]
    if specific:
        return specific[0]
    return h.limitations[0] if h.limitations else (h.counterarguments[0] if h.counterarguments else "n/a")


PEER_ROWS = ["revenue_cagr", "ebitda_cagr", "ebitda_margin", "debt_to_ebitda", "coverage", "cfo_to_ebitda"]


def peer_table(store: Store, run_id: str) -> Optional[dict]:
    """Company vs same-sector peers on the comparable figures (None when peers were not collected)."""
    from . import views
    from .peers import METRIC_NAMES
    peers = [p for p in store.peers(run_id) if not p.get("error")]
    failed = [p for p in store.peers(run_id) if p.get("error")]
    if not peers and not failed:
        return None
    own = views.context(store, run_id).own_profile()
    rows = []
    for k in PEER_ROWS:
        vals = [p["metrics"].get(k) for p in peers]
        if own.get(k) is None and all(v is None for v in vals):
            continue
        rows.append({"metric": METRIC_NAMES[k], "company": own.get(k), "peers": vals})
    return {"names": [p["name"] for p in peers], "symbols": [p["symbol"] for p in peers], "rows": rows,
            "unavailable": [f"{p['name']} ({p['error']})" for p in failed]}


def _story(dated: list[dict], n_docs: int) -> str:
    """When and how the change developed: first and latest evidence, and the sharpest move between periods."""
    if not dated:
        return ""
    first, last = dated[0]["period"], dated[-1]["period"]
    out = (f"First visible in {first}; latest evidence {last}" if first != last else f"Visible in {first}") + \
        f", from {n_docs} document(s)."
    best = None
    by_metric: dict = {}
    for r in dated:
        if isinstance(r.get("value"), (int, float)):
            by_metric.setdefault((r["metric"], r["unit"]), []).append(r)
    for (metric, unit), rows in by_metric.items():
        rows = sorted({r["period"]: r for r in rows}.values(), key=lambda r: period_sort_key(r["period"]))
        for a, b in zip(rows, rows[1:]):
            if a["value"] and a["value"] > 0:
                ch = (b["value"] - a["value"]) / a["value"] * 100
                if abs(ch) < 400 and (best is None or abs(ch) > abs(best[0])):
                    best = (ch, metric, a, b, unit)
    if best and abs(best[0]) >= 5:
        ch, metric, a, b, unit = best
        out += (f" The sharpest move: {metric} {'rose' if ch > 0 else 'fell'} {abs(ch):.0f}%, from "
                f"{fmt(a['value'], unit)} ({a['period']}) to {fmt(b['value'], unit)} ({b['period']}).")
    return out


def candidates(store: Store, run_id: str) -> list[tuple[Hypothesis, int]]:
    facts = {f.id: f for f in store.facts(run_id)}
    out = []
    for h in store.hypotheses(run_id):
        if h.status == HypothesisStatus.rejected:
            continue
        n_src = len({facts[i].source_id for i in h.supporting_fact_ids if i in facts})
        out.append((h, n_src))
    return sorted(out, key=lambda x: _rank(*x))


def build(store: Store, run_id: str, hyp_id: Optional[str] = None) -> Optional[dict]:
    """The Discovery brief for the best finding (or the one requested)."""
    from . import views  # local import: views imports heavy deps

    cands = candidates(store, run_id)
    if not cands:
        return None
    h = next((c for c, _ in cands if c.id == hyp_id), None) if hyp_id else cands[0][0]
    if h is None:
        return None
    p = views.passport(store, run_id, h.id)
    sup, sources = p["supporting"], p["sources"]

    # evidence grouped by document
    by_doc: "OrderedDict[str, dict]" = OrderedDict()
    for r in sup:
        d = by_doc.setdefault(r["source_id"], {"title": r["source_title"] or r["source_url"], "url": r["source_url"],
                                               "tier": r["source_tier"], "doc_type": r["doc_type"], "items": []})
        d["items"].append({"metric": r["metric"], "value": r["value"], "unit": r["unit"], "period": r["period"],
                           "page": r["page"], "passage": r["passage"], "link": views.web_url(r["source_url"], r["page"]),
                           "status": r["status"], "fact_id": r["id"]})

    # timeline: the dated facts behind the finding
    dated = [r for r in sup if r["period"]]
    dated.sort(key=lambda r: period_sort_key(r["period"]))
    timeline = [{"period": r["period"], "what": f"{r['metric']}: {fmt(r['value'], r['unit'])}",
                 "source": r["source_title"], "page": r["page"]} for r in dated]

    story = _story(dated, len(by_doc))
    checks = h.checks or []
    return {
        "hypothesis": h, "company": None,
        "discovery": h.statement.split(". ")[0].rstrip(".") + ".",
        "title": h.title, "direction": h.direction, "status": status_label(h.status), "strength": h.strength.value,
        "why": _why(h),
        "evidence": list(by_doc.values()), "n_sources": len(by_doc), "single_source": len(by_doc) < 2,
        "timeline": timeline, "emerged": timeline[0]["period"] if timeline else None, "story": story,
        "numbers": [c for c in p["calculations"] if c["result"] is not None],
        "counterargument": _counterargument(h, checks),
        "falsification": h.falsification or "n/a",
        "strength_reasons": _strength_reasons(h, sup, sources, checks),
        "non_obvious": is_non_obvious(h),
        "peers": peer_table(store, run_id),
        "peer_check": next((c for c in checks if c.get("check") == "sector_wide"), None),
        "alternatives": [{"id": c.id, "title": c.title, "status": status_label(c.status), "strength": c.strength.value}
                         for c, _ in cands[1:4]],
    }
