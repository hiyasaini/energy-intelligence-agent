"""Autonomous research loop.

Per round:  plan questions -> search -> fetch & parse -> extract facts -> run six modules ->
            generate / revise hypotheses -> plan counter-evidence + gap-fill queries for the next round.
Bounded by settings.max_rounds (default 3). Every step is wrapped so a failing source, provider or module is
logged as a research event and the partial results collected so far are kept.
"""
from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from .config import Settings, get_settings
from .db import Store
from .extraction.classify import classify_doc_type, classify_tier, company_domain_tokens, domain_of
from .extraction.documents import Document, parse_bytes
from .extraction.llm_extract import extract_with_llm
from .extraction.rules import ExtractionContext, document_default_period, extract_document
from .metrics import METRICS, metric_label
from .modules import AnalysisContext, run_all
from .providers.fetch import Fetcher, FetchResult, content_hash
from .providers.direct import DirectSources
from .providers.llm import LLMProvider, NullLLM, make_llm_provider
from .providers.search import NullSearch, SearchProvider, SearchResult, make_search_provider
from .schema import (Company, DocType, Fact, Hypothesis, Relationship, RelLabel, ResearchEvent, Run, Source,
                     SourceTier, now_iso)
from .verification import interpret, update_hypotheses

ProgressFn = Callable[[str, str, float], None]

DOC_PRIORITY = {DocType.annual_report: 1.0, DocType.investor_presentation: 0.95, DocType.quarterly_results: 0.9,
                DocType.exchange_filing: 0.85, DocType.rating_report: 0.8, DocType.announcement: 0.7,
                DocType.industry: 0.5, DocType.news: 0.45, DocType.other: 0.3}

# Generic research questions -> search templates. {name} is the resolved company name; {fy} recent FY.
BASE_QUESTIONS = [
    ("What did the latest annual report disclose?", "{name} annual report {fy} pdf"),
    ("What are the latest quarterly results?", "{name} quarterly results press release {fy}"),
    ("What does management guide to (capacity, capex, targets)?", "{name} investor presentation {fy} capacity target"),
    ("What has been filed with the exchanges recently?", "{name} NSE BSE announcement commissioning"),
    ("How do rating agencies view its debt?", "{name} credit rating rationale"),
    ("What do credible industry / media sources report?", "{name} capacity project delay financing news"),
]
GAP_QUERIES = {
    "capex_cr": "{name} capital expenditure capex {fy}",
    "gross_debt_cr": "{name} total borrowings debt {fy}",
    "finance_cost_cr": "{name} finance costs annual report {fy}",
    "cfo_cr": "{name} cash flow from operating activities {fy}",
    "generation_mu": "{name} generation million units {fy}",
    "installed_capacity_mw": "{name} installed capacity MW {fy}",
    "renewable_capacity_mw": "{name} renewable operational capacity MW",
    "revenue_cr": "{name} revenue from operations {fy}",
    "ebitda_cr": "{name} EBITDA {fy}",
    "receivables_cr": "{name} trade receivables {fy}",
    "capacity_under_construction_mw": "{name} capacity under construction pipeline MW",
}


@dataclass
class SeedDocument:
    """A user-supplied document (upload or local file). Treated exactly like a fetched source."""
    name: str
    data: bytes
    url: str = ""
    content_type: str = ""


@dataclass
class RunOutcome:
    run_id: str
    status: str
    rounds: int
    n_sources: int
    n_facts: int
    n_hypotheses: int
    errors: list[str] = field(default_factory=list)


def current_fy(today: Optional[date] = None) -> int:
    d = today or date.today()
    return d.year + 1 if d.month >= 4 else d.year


class ResearchAgent:
    def __init__(self, store: Store, settings: Optional[Settings] = None, search: Optional[SearchProvider] = None,
                 llm: Optional[LLMProvider] = None, fetcher=None, progress: Optional[ProgressFn] = None,
                 today: Optional[date] = None, direct=None):
        self.settings = settings or get_settings()
        # key-free exchange filings + financial tables; None disables (tests, demo)
        self.direct = direct if direct is not None else (DirectSources(self.settings.http_timeout)
                                                          if self.settings.direct_sources else None)
        self.store = store
        self.search = search if search is not None else make_search_provider(self.settings)
        self.llm = llm if llm is not None else make_llm_provider(self.settings)
        self.fetcher = fetcher or Fetcher(self.settings.cache_dir, self.settings.http_timeout, self.settings.user_agent)
        self.progress = progress or (lambda stage, msg, frac: None)
        self.today = today or date.today()
        self.run: Optional[Run] = None
        self._seen_urls: set[str] = set()
        self._seen_hashes: set[str] = set()
        self._queries_run: set[str] = set()
        self.errors: list[str] = []
        self.peer_profiles: list = []

    # -- logging ------------------------------------------------------------------------------
    def log(self, stage: str, msg: str, level: str = "info", rnd: int = 0, frac: float = -1) -> None:
        if self.run:
            self.store.upsert(ResearchEvent(run_id=self.run.id, round=rnd, stage=stage, level=level, message=msg))
        if level == "error":
            self.errors.append(msg)
        self.progress(stage, msg, frac)

    # -- public entry point -------------------------------------------------------------------
    def research(self, company: Company, mode: str = "live", seed_documents: Optional[list[SeedDocument]] = None,
                 seed_urls: Optional[list[str]] = None, max_rounds: Optional[int] = None) -> RunOutcome:
        max_rounds = max(1, min(int(max_rounds or self.settings.max_rounds), 5))
        self.run = Run(company=company, mode=mode, settings={
            **self.settings.describe(), "max_rounds": max_rounds, "search_provider": self.search.name,
            "llm_provider": self.llm.name, "seed_documents": [d.name for d in (seed_documents or [])],
            "seed_urls": list(seed_urls or [])})
        self.store.save_run(self.run)
        run_id = self.run.id
        self.log("start", f"Research started for {company.name} ({mode} mode). {company.resolution_note}".strip(), rnd=0,
                 frac=0.01)
        if mode == "demo":
            self.log("start", "DEMO MODE: all sources and figures are SYNTHETIC and do not describe any real company.",
                     "warning")
        if not self.search.available and not self.direct and not seed_documents and not seed_urls:
            self.log("plan", "No search provider configured and no documents supplied. Configure a search provider "
                             "in .env or upload documents. Modules will report insufficient data.", "warning")

        hyps: dict[str, Hypothesis] = {}
        searched_keys: set[str] = set()
        last_missing: list[str] = []
        try:
            for rnd in range(1, max_rounds + 1):
                base = (rnd - 1) / max_rounds
                step = 1 / max_rounds
                final = rnd == max_rounds
                # ---- 1. plan --------------------------------------------------------------------
                queries = self._plan(company, rnd, last_missing, hyps)
                if rnd == 1:
                    for d in seed_documents or []:
                        self._ingest_seed(d, rnd)
                    if self.direct and mode == "live":
                        self._ingest_direct(company, rnd)
                        self._collect_peers(company, rnd)
                    for u in seed_urls or []:
                        self._ingest_url(u, title=u, purpose="manual", rnd=rnd, query="(user supplied)", company=company)
                self.log("plan", f"Round {rnd}: {len(queries)} research question(s) planned.", rnd=rnd,
                         frac=base + 0.05 * step)
                # ---- 2. search & collect -------------------------------------------------------------
                counter_keys_this_round: set[str] = set()
                new_sources = 0
                if self.search.available and queries:
                    candidates: list[tuple[float, SearchResult, str, str]] = []
                    for q, purpose, keys in queries:
                        self._queries_run.add(q.lower())
                        try:
                            res = self.search.search(q, 8)
                        except Exception as e:
                            self.log("search", f"Search failed for '{q}': {type(e).__name__}: {str(e)[:150]}",
                                     "error", rnd)
                            continue
                        if purpose == "counterevidence":
                            counter_keys_this_round.update(keys)
                        kept = [r for r in res if self._relevant(r, company)]
                        self.log("search", f"'{q}' → {len(res)} result(s), {len(kept)} relevant.", rnd=rnd)
                        for r in kept:
                            candidates.append((self._rank_result(r, company, purpose), r, q, purpose))
                    candidates.sort(key=lambda x: -x[0])
                    budget = self.settings.max_sources_per_round
                    for score, r, q, purpose in candidates:
                        if budget <= 0:
                            break
                        if r.url in self._seen_urls:
                            continue
                        try:
                            src = self._ingest_url(r.url, r.title, purpose, rnd, q, company, r.date, r.snippet)
                        except Exception as e:
                            self.log("collect", f"Skipped {r.url}: {type(e).__name__}: {str(e)[:150]}", "warning", rnd)
                            continue
                        if src is not None:
                            budget -= 1
                            if src.fetch_status == "ok":
                                new_sources += 1
                    self.log("collect", f"Round {rnd}: {new_sources} new source(s) parsed.", rnd=rnd,
                             frac=base + 0.6 * step)
                searched_keys |= counter_keys_this_round
                if not self.search.available:
                    searched_keys |= set(hyps)  # cannot search; mark as checked against collected docs only

                # ---- 3. analyse & hypothesise ----------------------------------------------------------
                results, ctx = self._analyse(company, rnd)
                signals = [s for r in results.values() for s in r.signals]
                hyps_list = update_hypotheses(ctx, signals, hyps, rnd, searched_keys, final,
                                              search_available=self.search.available)
                hyps = {h.signal_key: h for h in hyps_list}
                self.store.delete_hypotheses(run_id)
                self.store.upsert_many(hyps_list)
                last_missing = sorted({m for r in results.values() for m in r.missing})
                n_by = {}
                for h in hyps_list:
                    n_by[h.status.value] = n_by.get(h.status.value, 0) + 1
                self.log("verify", f"Round {rnd}: {len(hyps_list)} hypothesis(es) — " +
                         ", ".join(f"{k}: {v}" for k, v in sorted(n_by.items())) + ".", rnd=rnd,
                         frac=base + 0.9 * step)
                self.run.rounds_completed = rnd
                self.store.save_run(self.run)
                if final:
                    break
                # stop early if the next round has nothing new to look for
                nxt = self._plan(company, rnd + 1, last_missing, hyps)
                if not nxt or not self.search.available:
                    self.log("plan", f"No further questions after round {rnd}; finalising.", rnd=rnd)
                    results, ctx = self._analyse(company, rnd)
                    signals = [s for r in results.values() for s in r.signals]
                    hyps_list = update_hypotheses(ctx, signals, hyps, rnd, searched_keys | set(hyps), True,
                                                  search_available=self.search.available)
                    hyps = {h.signal_key: h for h in hyps_list}
                    self.store.delete_hypotheses(run_id)
                    self.store.upsert_many(hyps_list)
                    break

            # ---- 4. interpretations (optional, guarded) + graph -------------------------------------
            if self.llm.available:
                ctx = self._context(company)
                for h in list(hyps.values())[:6]:
                    h.interpretation = interpret(h, ctx, self.llm)
                self.store.upsert_many(hyps.values())
            from .graph import persist_relationships
            persist_relationships(self.store, run_id)
            self.run.status = "partial" if self.errors else "completed"
        except Exception as e:  # keep everything collected so far
            self.log("run", f"Run stopped early: {type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}", "error")
            self.run.status = "partial"
        self.run.finished_at = now_iso()
        self.store.save_run(self.run)
        n_src = len([s for s in self.store.sources(run_id) if s.fetch_status == "ok"])
        n_f = len(self.store.facts(run_id))
        self.log("done", f"Finished: {n_src} source(s), {n_f} fact(s), {len(hyps)} hypothesis(es). "
                         f"Status: {self.run.status}.", frac=1.0)
        return RunOutcome(run_id, self.run.status, self.run.rounds_completed, n_src, n_f, len(hyps), self.errors)

    # -- planning -----------------------------------------------------------------------------
    def _plan(self, company: Company, rnd: int, missing_labels: list[str],
              hyps: dict[str, Hypothesis]) -> list[tuple[str, str, list[str]]]:
        fy = current_fy(self.today)
        name = company.name
        out: list[tuple[str, str, list[str]]] = []

        def add(q: str, purpose: str, keys: Optional[list[str]] = None):
            q = re.sub(r"\s+", " ", q).strip()
            if q.lower() in self._queries_run or any(q.lower() == x[0].lower() for x in out):
                return
            out.append((q, purpose, keys or []))

        if rnd == 1:
            for _, tmpl in BASE_QUESTIONS:
                add(tmpl.format(name=name, fy=f"FY{fy - 1}"), "discovery")
            if company.website:
                add(f"site:{domain_of('https://' + company.website.split('://')[-1])} investor annual report", "discovery")
            for q in self._llm_queries(company, missing_labels):
                add(q, "discovery")
            return out
        # gap-fill: metrics a module reported missing
        label_to_key = {metric_label(k): k for k in METRICS}
        for lab in missing_labels:
            k = label_to_key.get(lab)
            if k and k in GAP_QUERIES and len([x for x in out if x[1] == "gap_fill"]) < 4:
                add(GAP_QUERIES[k].format(name=name, fy=f"FY{fy - 1}"), "gap_fill")
        # counter-evidence for hypotheses not yet challenged externally
        pending = [h for h in hyps.values() if not h.counter_searched and h.counter_queries
                   and h.status.value not in ("rejected", "insufficient_evidence")]
        pending.sort(key=lambda h: -h.score)
        for h in pending[:5]:
            for q in h.counter_queries[:2]:
                add(q, "counterevidence", [h.signal_key])
        for q in self._llm_queries(company, missing_labels) if rnd == 2 else []:
            add(q, "gap_fill")
        return out

    def _llm_queries(self, company: Company, missing: list[str]) -> list[str]:
        if not self.llm.available:
            return []
        data = self.llm.complete_json(
            "You plan web searches for equity research on listed Indian energy companies.",
            f"Company: {company.name} (NSE: {company.nse or 'unknown'}; segment: {company.segment or 'unknown'}).\n"
            f"Metrics still missing: {', '.join(missing) or 'none'}.\n"
            "Propose up to 3 web search queries that would find primary disclosures (annual report, results, "
            "investor presentation, exchange filings). Return a JSON list of strings.")
        toks = [t for t in company_domain_tokens(company) if "." not in t] + [company.name.lower()]
        out = []
        for q in data if isinstance(data, list) else []:
            if isinstance(q, str) and 5 < len(q) < 160 and any(t in q.lower() for t in toks):
                out.append(q)
        return out[:3]

    # -- relevance & ranking --------------------------------------------------------------------
    def _relevant(self, r: SearchResult, company: Company) -> bool:
        if not r.url.lower().startswith(("http://", "https://", "synthetic://")):
            return False
        text = f"{r.title} {r.url} {r.snippet}".lower()
        toks = company_domain_tokens(company)
        if any(t in text for t in toks):
            return True
        core = [w for w in re.findall(r"[a-z]+", company.name.lower()) if len(w) >= 3 and
                w not in {"ltd", "limited", "the", "india", "and", "company"}]
        return bool(core) and all(w in text for w in core)

    def _rank_result(self, r: SearchResult, company: Company, purpose: str) -> float:
        tier = classify_tier(r.url, company)
        dt = classify_doc_type(r.url, r.title, r.snippet)
        from .schema import TIER_WEIGHT
        s = TIER_WEIGHT.get(tier, 0.3) + DOC_PRIORITY.get(dt, 0.3)
        if r.url.lower().endswith(".pdf"):
            s += 0.2
        if purpose == "counterevidence":
            s += 0.3  # ensure each round's challenges get fetched
        return s

    # -- ingestion ------------------------------------------------------------------------------
    def _ingest_direct(self, company: Company, rnd: int) -> None:
        self.log("collect", f"Looking up exchange filings and financial tables for NSE: {company.nse or 'n/a'}.",
                 rnd=rnd, frac=0.03)
        try:
            found = self.direct.discover(company.nse)
        except Exception as e:
            self.log("collect", f"Exchange filing lookup failed: {type(e).__name__}: {e}", "error", rnd)
            return
        for err in found.errors:
            self.log("collect", err, "warning", rnd)
        if found.digest:
            title, url, text = found.digest
            self._ingest_seed(SeedDocument(title, text.encode("utf-8"), url, "text/plain"), rnd, purpose="discovery",
                              query="(NSE announcements API)")
        n = 0
        for i, r in enumerate(found.results, 1):
            if r.url in self._seen_urls:
                continue
            self.log("collect", f"Reading {i}/{len(found.results)}: {r.title[:80]} (large annual reports can take a "
                                f"minute)", rnd=rnd, frac=0.05 + 0.25 * i / max(1, len(found.results)))
            try:
                src = self._ingest_url(r.url, r.title, "discovery", rnd, "(key-free exchange / financial sources)",
                                       company, r.date, r.snippet)
            except Exception as e:  # one bad document never stops the run
                self.log("collect", f"Skipped {r.url}: {type(e).__name__}: {str(e)[:150]}", "warning", rnd)
                continue
            n += 1 if src is not None and src.fetch_status == "ok" else 0
        self.log("collect", f"{n} of {len(found.results)} exchange / financial-table document(s) read.", rnd=rnd)

    def _ingest_url(self, url: str, title: str, purpose: str, rnd: int, query: str, company: Company,
                    published: Optional[str] = None, snippet: str = "") -> Optional[Source]:
        assert self.run
        self._seen_urls.add(url)
        src = Source(run_id=self.run.id, url=url, title=title[:200], doc_type=classify_doc_type(url, title, snippet),
                     tier=classify_tier(url, company), domain=domain_of(url), published=published,
                     query=query, purpose=purpose, round=rnd)
        try:
            fr: FetchResult = self.fetcher.fetch(url)
        except Exception as e:
            fr = FetchResult(url, False, error=f"{type(e).__name__}: {e}")
        if not fr.ok:
            src.fetch_status, src.error = "failed", fr.error
            self.store.upsert(src)
            self.log("fetch", f"Could not fetch {url}: {fr.error}", "warning", rnd)
            return src
        return self._process(src, fr.content, fr.content_type, rnd)

    def _ingest_seed(self, d: SeedDocument, rnd: int, purpose: str = "manual",
                     query: str = "(user supplied)") -> Optional[Source]:
        assert self.run
        url = d.url or f"upload://{d.name}"
        self._seen_urls.add(url)
        src = Source(run_id=self.run.id, url=url, title=d.name, doc_type=classify_doc_type(url, d.name),
                     tier=classify_tier(d.url, self.run.company) if d.url else SourceTier.unknown,
                     domain=domain_of(d.url) if d.url else "upload", query=query, purpose=purpose, round=rnd)
        return self._process(src, d.data, d.content_type, rnd)

    def _process(self, src: Source, data: bytes, ct: str, rnd: int) -> Optional[Source]:
        assert self.run
        h = content_hash(data)
        if h in self._seen_hashes:
            src.fetch_status, src.error = "skipped", "duplicate content of an earlier source"
            src.content_hash = h
            self.store.upsert(src)
            return src
        self._seen_hashes.add(h)
        src.content_hash = h
        try:
            doc: Document = parse_bytes(data, ct, src.url, self.settings.max_pdf_pages)
        except Exception as e:
            src.fetch_status, src.error = "failed", f"parse error: {type(e).__name__}: {e}"
            self.store.upsert(src)
            self.log("parse", f"Could not parse {src.url}: {src.error}", "warning", rnd)
            return src
        if doc.title and (not src.title or src.title == src.url):
            src.title = doc.title[:200]
        if src.doc_type == DocType.other:
            src.doc_type = classify_doc_type(src.url, src.title, doc.full_text[:1500])
        src.published = src.published or doc.published_hint
        src.n_pages = len(doc.pages)
        if not doc.full_text.strip():
            src.fetch_status, src.error = "failed", "no extractable text (scanned PDF or empty page)"
            self.store.upsert(src)
            self.log("parse", f"No text in {src.url} (scanned or empty).", "warning", rnd)
            return src
        src.fetch_status = "ok"
        self.store.save_pages(self.run.id, src.id, [(pg.number, pg.text) for pg in doc.pages if pg.text.strip()])
        for w in doc.warnings:
            self.log("parse", f"{src.title or src.url}: {w}", "warning", rnd)
        co = self.run.company
        words = tuple(w for w in [co.nse, *(co.name or "").replace(" Ltd", "").split()[:1],
                                  *[a.strip() for a in (co.aliases or [])]]
                      if w and len(w) >= 3 and w.lower() not in ("the", "indian", "india", "national"))
        ectx = ExtractionContext(self.run.id, src.id, is_synthetic=src.tier == SourceTier.synthetic,
                                 scope_hint=f"{src.url} {src.title}", company_words=words)
        try:
            facts = extract_document(doc, ectx)
        except Exception as e:
            facts = []
            self.log("extract", f"Rule extraction failed on {src.url}: {type(e).__name__}: {e}", "error", rnd)
        if self.llm.available:
            kw = re.compile("|".join(p.pattern for m in METRICS.values() for p in m.patterns[:2]), re.I)
            try:
                lf, dropped = extract_with_llm(doc, ectx, self.llm, max_pages=8, page_filter=lambda t: bool(kw.search(t)))
                facts += lf
                if dropped:
                    self.log("extract", f"{dropped} LLM proposal(s) discarded as not grounded in {src.title[:60]}.",
                             rnd=rnd)
            except Exception as e:
                self.log("extract", f"LLM extraction failed: {type(e).__name__}", "warning", rnd)
        self._date_checks(src, ectx.default_period, rnd)
        self.store.upsert(src)
        self.store.upsert_many(facts)
        self.store.upsert_many([Relationship(run_id=self.run.id, src_type="fact", src_id=f.id, dst_type="source",
                                             dst_id=src.id, relation="extracted_from",
                                             label=RelLabel.observed if f.status.value == "source_verified"
                                             else RelLabel.unverified, note=f"page {f.page}" if f.page else "")
                                for f in facts])
        n_t = sum(1 for f in facts if f.fact_type.value == "target")
        n_e = sum(1 for f in facts if f.fact_type.value == "event")
        self.log("extract", f"{src.title[:70] or src.url}: {len(doc.pages)} page(s) → {len(facts)} fact(s) "
                            f"({n_t} target, {n_e} event).", rnd=rnd)
        return src

    def _date_checks(self, src: Source, doc_period: Optional[str], rnd: int) -> None:
        from .periods import period_sort_key
        if doc_period:
            fy = period_sort_key(doc_period)[0]
            if fy and current_fy(self.today) - fy >= 4:
                self.log("verify", f"{src.title[:60]}: reports on {doc_period}, which is ≥4 years old; "
                                   "treated as historical context.", "warning", rnd)
        if src.published:
            try:
                if date.fromisoformat(src.published[:10]) > self.today:
                    self.log("verify", f"{src.title[:60]}: publication date {src.published} is in the future; "
                                       "date ignored.", "warning", rnd)
                    src.published = None
            except ValueError:
                src.published = None

    # -- analysis -------------------------------------------------------------------------------
    def _context(self, company: Company) -> AnalysisContext:
        assert self.run
        ctx = AnalysisContext(self.run.id, company, self.store.facts(self.run.id), self.store.sources(self.run.id))
        ctx.peers = self.peer_profiles
        return ctx

    def _collect_peers(self, company: Company, rnd: int) -> None:
        """Same-sector listed peers, read with the same rules, to tell company stories from sector stories."""
        if self.settings.peers <= 0:
            return
        from .identity import load_registry
        from .peers import collect

        def extract(doc, sym):
            return extract_document(doc, ExtractionContext(f"peer:{sym}", f"peer:{sym}", scope_hint="/consolidated/"))
        try:
            self.peer_profiles = collect(company, load_registry(), self.fetcher.fetch,
                                         lambda b, ct, u: parse_bytes(b, ct, u, 40), extract, self.settings.peers)
        except Exception as e:  # peers are optional evidence; never stop the run
            self.log("peers", f"Peer comparison skipped: {type(e).__name__}: {str(e)[:120]}", "warning", rnd)
            return
        ok = [p for p in self.peer_profiles if not p.error]
        if self.peer_profiles:
            self.log("peers", f"Peer comparison: {', '.join(p.name for p in ok) or 'none readable'}"
                     + (f" ({len(self.peer_profiles) - len(ok)} unavailable)" if len(ok) < len(self.peer_profiles) else "")
                     + ".", rnd=rnd)
        else:
            self.log("peers", "No same-sector peers in the registry; peer comparison not available.", rnd=rnd)
        self.store.save_peers(self.run.id, self.peer_profiles)

    def _analyse(self, company: Company, rnd: int):
        assert self.run
        ctx = self._context(company)
        self.store.clear_derived(self.run.id)
        results = run_all(ctx)
        for r in results.values():
            if r.status == "error":
                self.log("analyse", f"{r.name}: {r.summary}", "error", rnd)
            self.store.upsert_many(r.calcs)
            self.store.upsert_many(r.relationships)
        self.store.save_module_results(self.run.id, results, rnd)
        ok = sum(1 for r in results.values() if r.status == "ok")
        self.log("analyse", f"Round {rnd}: {len(ctx.facts)} fact(s) analysed; {ok}/6 module(s) with sufficient data.",
                 rnd=rnd)
        return results, ctx
