"""HTTP fetching with on-disk cache. Failures are returned, never raised, so research can continue."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

MAX_BYTES = 150 * 1024 * 1024  # annual reports on NSE are often 30-100 MB


@dataclass
class FetchResult:
    url: str
    ok: bool
    content: bytes = b""
    content_type: str = ""
    final_url: str = ""
    error: str = ""
    from_cache: bool = False


class Fetcher:
    def __init__(self, cache_dir: str, timeout: int = 25, user_agent: str = "EnergyIntelligenceAgent/0.1"):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "text/html,application/pdf,*/*;q=0.8",
                                     "Accept-Language": "en-IN,en;q=0.9"})
        ca = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
        if ca and Path(ca).exists():
            self.session.verify = ca

    def _key(self, url: str) -> Path:
        return self.cache / hashlib.sha256(url.encode()).hexdigest()[:32]

    def fetch(self, url: str) -> FetchResult:
        key = self._key(url)
        if key.exists() and key.with_suffix(".ct").exists():
            return FetchResult(url, True, key.read_bytes(), key.with_suffix(".ct").read_text(), url, from_cache=True)
        if not url.lower().startswith(("http://", "https://")):
            return FetchResult(url, False, error="unsupported URL scheme")
        try:
            if "nseindia.com" in url and not getattr(self, "_nse_warm", False):
                try:  # NSE archives expect the cookies a browser gets from the home page
                    self.session.get("https://www.nseindia.com", timeout=self.timeout)
                except requests.RequestException:
                    pass
                self._nse_warm = True
            headers = {"Referer": "https://www.nseindia.com/"} if "nseindia.com" in url else {}
            r = self.session.get(url, timeout=self.timeout, stream=True, allow_redirects=True, headers=headers)
            if r.status_code >= 400:
                return FetchResult(url, False, error=f"HTTP {r.status_code}", final_url=r.url)
            chunks, size = [], 0
            for ch in r.iter_content(65536):
                size += len(ch)
                if size > MAX_BYTES:
                    return FetchResult(url, False, error="document exceeds size limit", final_url=r.url)
                chunks.append(ch)
            data = b"".join(chunks)
            ct = r.headers.get("Content-Type", "")
            key.write_bytes(data)
            key.with_suffix(".ct").write_text(ct)
            return FetchResult(url, True, data, ct, r.url)
        except requests.RequestException as e:
            return FetchResult(url, False, error=f"{type(e).__name__}: {str(e)[:200]}")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def load_local_file(path: str) -> Optional[FetchResult]:
    p = Path(path)
    if not p.exists():
        return None
    data = p.read_bytes()
    ct = "application/pdf" if data[:5] == b"%PDF-" else ("text/html" if p.suffix.lower() in (".html", ".htm")
                                                          else "text/plain")
    return FetchResult(f"file://{p.resolve()}", True, data, ct, f"file://{p.resolve()}")
