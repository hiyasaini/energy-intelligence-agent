"""Classify a source URL/title into document type and credibility tier (generic, domain-based)."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from ..schema import Company, DocType, SourceTier

EXCHANGE = ("nseindia.com", "bseindia.com")
REGULATOR = ("cea.nic.in", "mnre.gov.in", "cercind.gov.in", "sebi.gov.in", "pib.gov.in", "powermin.gov.in",
             "seci.co.in", "grid-india.in", "posoco.in", "niti.gov.in", "gov.in", "nic.in")
RATING = ("crisil.com", "icra.in", "careratings.com", "careedge.in", "indiaratings.co.in", "acuite.in",
          "infomerics.com", "brickworkratings.com", "moodys.com", "spglobal.com", "fitchratings.com")
MEDIA = ("economictimes.indiatimes.com", "livemint.com", "business-standard.com", "moneycontrol.com",
         "reuters.com", "thehindubusinessline.com", "financialexpress.com", "bloomberg.com", "ft.com",
         "mercomindia.com", "pv-magazine-india.com", "energyworld.com", "cnbctv18.com", "ndtvprofit.com",
         "thehindu.com", "hindustantimes.com", "pv-tech.org", "renewablewatch.in", "saurenergy.com")
AGGREGATOR = ("screener.in", "tickertape.in", "trendlyne.com", "moneycontrol.com", "valueresearchonline.com")
INDUSTRY = ("iea.org", "irena.org", "ember-energy.org", "ieefa.org", "cseindia.org", "teriin.org", "jmkresearch.com")


def domain_of(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return d[4:] if d.startswith("www.") else d


def _matches(domain: str, suffixes: tuple[str, ...]) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in suffixes)


def company_domain_tokens(company: Company) -> list[str]:
    toks = set()
    if company.website:
        toks.add(domain_of(company.website if "://" in company.website else "https://" + company.website))
    stop = {"limited", "ltd", "india", "the", "and", "company", "corporation", "of", "power", "energy", "energies"}
    for w in re.findall(r"[a-z]+", company.name.lower()):
        if w not in stop and len(w) >= 4:
            toks.add(w)
    for t in (company.nse, company.bse):
        if t and not t.isdigit() and len(t) >= 3:
            toks.add(t.lower())
    return sorted(toks)


def classify_tier(url: str, company: Optional[Company] = None) -> SourceTier:
    if url.startswith("synthetic://"):
        return SourceTier.synthetic
    d = domain_of(url)
    if _matches(d, EXCHANGE):
        return SourceTier.exchange
    if _matches(d, RATING):
        return SourceTier.rating_agency
    if _matches(d, MEDIA) or _matches(d, AGGREGATOR):
        return SourceTier.media
    if company:
        for t in company_domain_tokens(company):
            if t and (t in d.split(".")[0] or d == t or (("." in t) and d.endswith(t))):
                return SourceTier.company
    if _matches(d, REGULATOR):
        return SourceTier.regulator
    return SourceTier.unknown


def classify_doc_type(url: str, title: str = "", snippet: str = "") -> DocType:
    t = f"{url} {title} {snippet}".lower()
    if re.search(r"annual[\s_-]*report|integrated[\s_-]*report|\bar[\s_-]?20\d{2}", t):
        return DocType.annual_report
    if re.search(r"investor[\s_-]*presentation|earnings[\s_-]*presentation|analyst[\s_-]*(meet|presentation)|investor[\s_-]*deck", t):
        return DocType.investor_presentation
    if re.search(r"(quarterly|financial)[\s_-]*results?|q[1-4][\s_-]*fy|results?[\s_-]*for[\s_-]*the[\s_-]*quarter|press[\s_-]*release.*result", t):
        return DocType.quarterly_results
    if re.search(r"rating[\s_-]*(rationale|action)|credit[\s_-]*rating|rationale", t):
        return DocType.rating_report
    if re.search(r"nseindia|bseindia|corporate[\s_-]*announcement|disclosure[\s_-]*under[\s_-]*regulation|\blodr\b", t):
        return DocType.exchange_filing
    if re.search(r"announce|press[\s_-]*release|commission|awarded|newsroom|media", t):
        return DocType.announcement
    if re.search(r"cea\.nic|mnre|cerc|installed[\s_-]*capacity[\s_-]*report|iea|irena|ember", t):
        return DocType.industry
    if any(m in t for m in MEDIA):
        return DocType.news
    return DocType.other
