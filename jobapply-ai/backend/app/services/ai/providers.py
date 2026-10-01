"""Provider abstraction. Each adapter implements one method: complete(system, user, model, max_tokens) -> text."""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.core.config import Settings


class ProviderError(Exception):
    pass


class AIProvider(ABC):
    name: str = "base"
    cheap_model: str = ""
    strong_model: str = ""

    @abstractmethod
    def complete(self, *, system: str, user: str, model: str, max_tokens: int, json_mode: bool = True) -> str: ...


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, base_url: str, cheap: str, strong: str, name: str = "openai"):
        self.api_key, self.base_url = api_key, base_url.rstrip("/")
        self.cheap_model, self.strong_model, self.name = cheap, strong, name

    def complete(self, *, system, user, model, max_tokens, json_mode=True):
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": 0.2}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=90)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"{self.name}: {type(exc).__name__}") from exc


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, cheap: str, strong: str):
        self.api_key, self.cheap_model, self.strong_model = api_key, cheap, strong

    def complete(self, *, system, user, model, max_tokens, json_mode=True):
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0.2, "system": system,
                "messages": [{"role": "user", "content": user}]}
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=90,
                           headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ProviderError(f"anthropic: {type(exc).__name__}") from exc


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, cheap: str, strong: str):
        self.api_key, self.cheap_model, self.strong_model = api_key, cheap, strong

    def complete(self, *, system, user, model, max_tokens, json_mode=True):
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2,
                                     **({"responseMimeType": "application/json"} if json_mode else {})}}
        try:
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                           json=body, headers={"x-goog-api-key": self.api_key}, timeout=90)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"gemini: {type(exc).__name__}") from exc


def build_provider(s: Settings) -> AIProvider | None:
    """Return a configured LLM provider or None (→ heuristic mode)."""
    p = s.ai_provider.lower()
    if p == "openai" and s.openai_api_key:
        return OpenAIProvider(s.openai_api_key, s.openai_base_url, s.ai_cheap_model or "gpt-4o-mini", s.ai_strong_model or "gpt-4o")
    if p == "openai_compatible" and s.openai_base_url:
        return OpenAIProvider(s.openai_api_key or "none", s.openai_base_url, s.ai_cheap_model, s.ai_strong_model or s.ai_cheap_model, name="openai_compatible")
    if p == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.anthropic_api_key, s.ai_cheap_model or "claude-haiku-4-5-20251001", s.ai_strong_model or "claude-sonnet-5-5")
    if p == "gemini" and s.gemini_api_key:
        return GeminiProvider(s.gemini_api_key, s.ai_cheap_model or "gemini-2.0-flash", s.ai_strong_model or "gemini-2.0-flash")
    return None
