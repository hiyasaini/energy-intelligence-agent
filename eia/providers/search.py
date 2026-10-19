"""Pluggable web search. Choose with EIA_SEARCH_PROVIDER = tavily | serper | brave | anthropic | duckduckgo | none."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    date: Optional[str] = None


class SearchError(RuntimeError):
    pass


class SearchProvider:
    name = "base"
    available = True

    def search(self, query: str, n: int = 8) -> list[SearchResult]:  # pragma: no cover - interface
        raise NotImplementedError


class NullSearch(SearchProvider):
    name = "none"
    available = False

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        return []


class StaticSearch(SearchProvider):
    """Deterministic provider for tests/offline runs: maps query substrings to canned results."""
    name = "static"

    def __init__(self, table: dict[str, list[SearchResult]]):
        self.table = table
        self.queries: list[str] = []

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        self.queries.append(query)
        out = []
        for k, v in self.table.items():
            if k.lower() in query.lower():
                out.extend(v)
        return out[:n]


class TavilySearch(SearchProvider):
    name = "tavily"

    def __init__(self, key: str, timeout: int = 20):
        self.key, self.timeout = key, timeout

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        r = requests.post("https://api.tavily.com/search", timeout=self.timeout,
                          headers={"Authorization": f"Bearer {self.key}"},
                          json={"api_key": self.key, "query": query, "max_results": n, "search_depth": "basic"})
        if r.status_code >= 400:
            raise SearchError(f"Tavily HTTP {r.status_code}")
        return [SearchResult(x.get("title", ""), x.get("url", ""), x.get("content", "")[:400], x.get("published_date"))
                for x in r.json().get("results", []) if x.get("url")]


class SerperSearch(SearchProvider):
    name = "serper"

    def __init__(self, key: str, timeout: int = 20):
        self.key, self.timeout = key, timeout

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        r = requests.post("https://google.serper.dev/search", timeout=self.timeout,
                          headers={"X-API-KEY": self.key}, json={"q": query, "num": n, "gl": "in"})
        if r.status_code >= 400:
            raise SearchError(f"Serper HTTP {r.status_code}")
        return [SearchResult(x.get("title", ""), x.get("link", ""), x.get("snippet", ""), x.get("date"))
                for x in r.json().get("organic", []) if x.get("link")]


class BraveSearch(SearchProvider):
    name = "brave"

    def __init__(self, key: str, timeout: int = 20):
        self.key, self.timeout = key, timeout

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        r = requests.get("https://api.search.brave.com/res/v1/web/search", timeout=self.timeout,
                         headers={"X-Subscription-Token": self.key, "Accept": "application/json"},
                         params={"q": query, "count": n, "country": "IN"})
        if r.status_code >= 400:
            raise SearchError(f"Brave HTTP {r.status_code}")
        return [SearchResult(x.get("title", ""), x.get("url", ""), x.get("description", ""), x.get("age"))
                for x in r.json().get("web", {}).get("results", []) if x.get("url")]


class AnthropicWebSearch(SearchProvider):
    """Uses the Anthropic Messages API server-side web search tool; returns only URLs the tool returned."""
    name = "anthropic"

    def __init__(self, key: str, model: str, timeout: int = 60):
        self.key, self.model, self.timeout = key, model, timeout

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        r = requests.post(
            "https://api.anthropic.com/v1/messages", timeout=self.timeout,
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 512,
                  "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                  "messages": [{"role": "user", "content": f"Search the web for: {query}. Do not answer; just search."}]})
        if r.status_code >= 400:
            raise SearchError(f"Anthropic HTTP {r.status_code}: {r.text[:200]}")
        out = []
        for block in r.json().get("content", []):
            if block.get("type") == "web_search_tool_result" and isinstance(block.get("content"), list):
                for x in block["content"]:
                    if x.get("type") == "web_search_result" and x.get("url"):
                        out.append(SearchResult(x.get("title", ""), x["url"], "", x.get("page_age")))
        return out[:n]


class DuckDuckGoSearch(SearchProvider):
    """Keyless HTML endpoint. Fragile by nature; used only when chosen explicitly."""
    name = "duckduckgo"

    def __init__(self, timeout: int = 20, user_agent: str = "Mozilla/5.0"):
        self.timeout, self.ua = timeout, user_agent

    def search(self, query: str, n: int = 8) -> list[SearchResult]:
        from bs4 import BeautifulSoup
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "in-en"},
                          headers={"User-Agent": self.ua}, timeout=self.timeout)
        if r.status_code >= 400:
            raise SearchError(f"DuckDuckGo HTTP {r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for res in soup.select(".result"):
            a = res.select_one("a.result__a")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
            sn = res.select_one(".result__snippet")
            out.append(SearchResult(a.get_text(" ", strip=True), href, sn.get_text(" ", strip=True) if sn else ""))
            if len(out) >= n:
                break
        return out


def make_search_provider(settings) -> SearchProvider:
    p = settings.search_provider
    if p == "tavily" and settings.tavily_api_key:
        return TavilySearch(settings.tavily_api_key, settings.http_timeout)
    if p == "serper" and settings.serper_api_key:
        return SerperSearch(settings.serper_api_key, settings.http_timeout)
    if p == "brave" and settings.brave_api_key:
        return BraveSearch(settings.brave_api_key, settings.http_timeout)
    if p == "anthropic" and settings.anthropic_api_key:
        return AnthropicWebSearch(settings.anthropic_api_key, settings.anthropic_model)
    if p == "duckduckgo":
        return DuckDuckGoSearch(settings.http_timeout, settings.user_agent)
    return NullSearch()


def is_probably_document(url: str) -> bool:
    u = url.lower()
    return u.endswith(".pdf") or bool(re.search(r"/(investor|investors|annual|results|financial|media|press)", u))
