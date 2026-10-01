"""AIService — the single entry point for structured LLM calls.

Responsibilities: model routing (cheap/strong tiers), content-hash cache, token/char caps, schema validation,
bounded retries, heuristic fallback, and metadata-only request logging (no prompt/response content).
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import sha256_hex
from app.models import AICache, AIRequestLog, UsageRecord
from app.services.ai.providers import AIProvider, ProviderError, build_provider
from app.services.ai.safety import SYSTEM_RULES

T = TypeVar("T", bound=BaseModel)

# Rough $/1M-token prices (input, output) used ONLY for usage estimates shown to the user.
_PRICE_HINT = {"cheap": (0.15, 0.60), "strong": (2.5, 10.0)}


class AIUnavailable(Exception):
    """No provider configured or all attempts failed and no fallback allowed."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


class AIService:
    def __init__(self, db: Session, user_id: uuid.UUID | None, provider: AIProvider | None = None):
        self.db = db
        self.user_id = user_id
        self.settings = get_settings()
        self.provider = provider if provider is not None else build_provider(self.settings)

    @property
    def llm_enabled(self) -> bool:
        return self.provider is not None

    def structured(
        self,
        *,
        task: str,
        user_prompt: str,
        schema: type[T],
        tier: str = "cheap",
        fallback: Callable[[], T] | None = None,
        system_extra: str = "",
        cache: bool = True,
    ) -> tuple[T, str]:
        """Return (validated_result, source) where source is 'llm', 'cache' or 'heuristic'."""
        s = self.settings
        if not self.provider:
            if fallback:
                return fallback(), "heuristic"
            raise AIUnavailable("No AI provider configured")

        model = (self.provider.cheap_model if tier == "cheap" else self.provider.strong_model) or self.provider.cheap_model
        schema_hint = json.dumps(schema.model_json_schema().get("properties", {}), separators=(",", ":"))[:3500]
        system = f"{SYSTEM_RULES}\n{system_extra}\nJSON schema (properties): {schema_hint}"
        prompt = user_prompt[: s.ai_max_input_chars]
        key = sha256_hex(f"{task}|{self.provider.name}|{model}|{system}|{prompt}")

        if cache:
            hit = self.db.get(AICache, key)
            if hit:
                try:
                    out = schema.model_validate(hit.value)
                    self._log(task, model, len(prompt), 0, 0, True, True, None)
                    return out, "cache"
                except ValidationError:
                    pass

        last_err = "unknown"
        attempts = 1 + max(0, s.ai_max_retries)
        err_note = ""
        for attempt in range(attempts):
            t0 = time.monotonic()
            try:
                raw = self.provider.complete(system=system, user=prompt + err_note, model=model, max_tokens=s.ai_max_output_tokens)
                data = _extract_json(raw)
                result = schema.model_validate(data)
            except (ProviderError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_err = type(exc).__name__
                err_note = f"\n\nYour previous reply was invalid ({last_err}). Return ONLY valid JSON matching the schema."
                self._log(task, model, len(prompt), 0, int((time.monotonic() - t0) * 1000), False, False, last_err)
                continue
            self._log(task, model, len(prompt), len(raw), int((time.monotonic() - t0) * 1000), True, False, None)
            self._usage(task, tier, len(prompt), len(raw))
            if cache:
                self.db.merge(AICache(key=key, task=task, value=result.model_dump(mode="json")))
                self.db.flush()
            return result, "llm"

        if fallback and s.ai_fallback_to_heuristic:
            return fallback(), "heuristic"
        raise AIUnavailable(f"AI task '{task}' failed ({last_err})")

    # ---- bookkeeping -------------------------------------------------
    def _log(self, task, model, in_chars, out_chars, latency, success, cache_hit, error):
        self.db.add(AIRequestLog(user_id=self.user_id, task=task, provider=self.provider.name if self.provider else "heuristic", model=model,
                                 input_chars=in_chars, output_chars=out_chars, latency_ms=latency, cache_hit=cache_hit,
                                 success=success, error=error))

    def _usage(self, task: str, tier: str, in_chars: int, out_chars: int) -> None:
        if not self.user_id:
            return
        in_tok, out_tok = in_chars // 4, out_chars // 4
        pi, po = _PRICE_HINT.get(tier, _PRICE_HINT["cheap"])
        micros = int(in_tok * pi + out_tok * po)  # (tokens * $/1M) * 1e6 / 1e6 → micro-dollars
        self.db.add(UsageRecord(user_id=self.user_id, metric="ai_tokens", quantity=1, input_tokens=in_tok, output_tokens=out_tok,
                                est_cost_usd_micros=micros, meta={"task": task, "tier": tier}))
