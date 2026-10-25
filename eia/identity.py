"""Company identity resolution. Never auto-picks between close candidates.

The registry (data/companies.csv) holds identity metadata only: legal name, NSE symbol, aliases, segment,
website. It contains no financial facts or findings. Companies outside the registry can still be researched
as 'unregistered' with an explicit warning.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .schema import Company

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "companies.csv"
GENERIC = {"ltd", "limited", "india", "the", "company", "corporation", "corp", "of", "and", "co", "power",
           "energy", "energies", "green", "renewable", "renewables", "solar", "wind", "gas", "oil", "private"}


@dataclass
class Resolution:
    status: str                          # resolved | ambiguous | not_found
    company: Optional[Company] = None
    candidates: list[tuple[Company, float]] = field(default_factory=list)
    message: str = ""


def load_registry(path: Path = REGISTRY) -> list[Company]:
    out = []
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(Company(name=r["name"].strip(), nse=r.get("nse", "").strip(), bse=r.get("bse", "").strip(),
                               aliases=[a.strip() for a in (r.get("aliases") or "").split("|") if a.strip()],
                               segment=r.get("segment", "").strip(), website=r.get("website", "").strip(),
                               eligible=not r.get("segment", "").strip().lower().startswith(NON_ENERGY)))
    return out


NON_ENERGY = "non-energy"
OUTSIDE_TRACK = ("Outside Track B (energy, power & renewables): only the general financial checks apply; capacity, "
                 "production and energy-specific findings are not expected.")


def _note(c: Company, note: str) -> Company:
    return c.model_copy(update={"resolution_note": note + ("" if c.eligible else " " + OUTSIDE_TRACK)})


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if t}


LEGAL = {"ltd", "limited", "the", "co", "company", "pvt", "private", "inc"}


def _core(s: str) -> str:
    return " ".join(t for t in _norm(s).split() if t not in LEGAL)


def _score(q: str, c: Company) -> float:
    qn = _core(q)
    names = [c.name] + c.aliases
    best = 0.0
    for n in names:
        nn = _core(n)
        if qn == nn:
            return 1.0
        best = max(best, SequenceMatcher(None, qn, nn).ratio())
        qt, nt = _tokens(q), _tokens(n)
        dq = qt - GENERIC
        if dq and dq <= nt:
            # all distinctive query tokens present in the name
            best = max(best, 0.85 + 0.1 * len(qt & nt) / max(len(nt), 1))
    return best


def resolve(query: str, registry: Optional[list[Company]] = None) -> Resolution:
    q = (query or "").strip()
    if len(q) < 2:
        return Resolution("not_found", message="Enter a company name or NSE symbol.")
    reg = registry if registry is not None else load_registry()
    # exact ticker
    tick = [c for c in reg if q.upper() in (c.nse.upper(), c.bse.upper()) and q.upper()]
    if len(tick) == 1:
        c = _note(tick[0], f"Exact symbol match '{q.upper()}'.")
        return Resolution("resolved", c, [(c, 1.0)])
    scored = sorted(((c, _score(q, c)) for c in reg), key=lambda x: -x[1])
    scored = [(c, s) for c, s in scored if s >= 0.6]
    if not scored:
        return Resolution("not_found", message=f"'{q}' is not in the registry (listed energy companies and the NIFTY 50). "
                                                "You may research it as an unregistered name (identity unverified).")
    top = scored[0]
    close = [x for x in scored if top[1] - x[1] < 0.08]
    if top[1] >= 0.999 and len([x for x in scored if x[1] >= 0.999]) == 1:
        c = _note(top[0], "Exact name/alias match.")
        return Resolution("resolved", c, scored[:5])
    if len(close) == 1 and top[1] >= 0.85:
        c = _note(top[0], f"Best match (score {top[1]:.2f}); no close alternative.")
        return Resolution("resolved", c, scored[:5])
    return Resolution("ambiguous", None, scored[:6],
                      f"'{q}' matches several listed companies; choose one explicitly.")


def unregistered(name: str) -> Company:
    return Company(name=name.strip(), eligible=True,
                   resolution_note="UNREGISTERED: identity not verified against the registry; "
                                   "confirm listing status from exchange sources.")
