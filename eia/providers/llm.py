"""Pluggable LLM. Choose with EIA_LLM_PROVIDER = anthropic | openai | none.

The LLM is used only for: planning extra research questions, proposing structured facts (which are then
verified against the page text), and writing labelled interpretations. It is never asked to do arithmetic.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import requests


class LLMError(RuntimeError):
    pass


class LLMProvider:
    name = "base"
    available = True

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:  # pragma: no cover
        raise NotImplementedError

    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> Optional[Any]:
        try:
            txt = self.complete(system + "\nRespond with JSON only, no prose.", user, max_tokens)
        except Exception:
            return None
        return parse_json_block(txt)


def parse_json_block(txt: str) -> Optional[Any]:
    if not txt:
        return None
    m = re.search(r"```(?:json)?\s*(.+?)```", txt, re.S)
    body = m.group(1) if m else txt
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = body.find(opener), body.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(body[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


class NullLLM(LLMProvider):
    name = "none"
    available = False

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        return ""

    def complete_json(self, system: str, user: str, max_tokens: int = 2000):
        return None


class StaticLLM(LLMProvider):
    """Test double: returns a fixed response (or a callable's output)."""
    name = "static"

    def __init__(self, response):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        self.calls.append((system, user))
        return self.response(system, user) if callable(self.response) else self.response


class AnthropicLLM(LLMProvider):
    name = "anthropic"

    def __init__(self, key: str, model: str, timeout: int = 90):
        self.key, self.model, self.timeout = key, model, timeout

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=self.timeout,
                          headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": self.model, "max_tokens": max_tokens, "system": system,
                                "messages": [{"role": "user", "content": user}]})
        if r.status_code >= 400:
            raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:200]}")
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


class OpenAICompatLLM(LLMProvider):
    name = "openai"

    def __init__(self, key: str, base_url: str, model: str, timeout: int = 90):
        self.key, self.base, self.model, self.timeout = key, base_url.rstrip("/"), model, timeout

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        r = requests.post(f"{self.base}/chat/completions", timeout=self.timeout,
                          headers={"Authorization": f"Bearer {self.key}"},
                          json={"model": self.model, "max_tokens": max_tokens, "temperature": 0,
                                "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": user}]})
        if r.status_code >= 400:
            raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:200]}")
        return r.json()["choices"][0]["message"]["content"] or ""


def make_llm_provider(settings) -> LLMProvider:
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAICompatLLM(settings.openai_api_key, settings.openai_base_url, settings.openai_model)
    return NullLLM()
