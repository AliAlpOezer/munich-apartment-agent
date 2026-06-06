"""Tiered model router — mirrors the customOpenClaw philosophy.

Tier 1 (cheap)  : OpenRouter free models   -> structural / easy work
Tier 2 (medium) : OpenCode Zen             -> normal reasoning, fit-ranking
Tier 3 (hard)   : Anthropic Claude         -> only when escalation is warranted

`complete`/`structured` try the requested tier, rotate through the models *within* a
tier (free models rate-limit hard), and escalate to higher tiers on error — bounded by
`max_tier`. Chat models are constructed lazily and cached, so importing/compiling the
graph needs neither keys nor network.
"""

from __future__ import annotations

import logging
from enum import IntEnum

from pydantic import BaseModel

from apartment_agent.config import Settings

log = logging.getLogger(__name__)


class Tier(IntEnum):
    CHEAP = 1
    MEDIUM = 2
    HARD = 3


class ModelRouter:
    def __init__(self, settings: Settings):
        self.s = settings
        self._cache: dict[tuple[str, str], object] = {}

    # -- tier -> [(provider, model_id), ...] ---------------------------------
    def models_for_tier(self, tier: Tier) -> list[tuple[str, str]]:
        if tier is Tier.CHEAP:
            # OpenCode Zen free models (OpenRouter's free models proved rate-limited/deprecated).
            return [("opencode", m) for m in self.s.tier1_model_list]
        if tier is Tier.MEDIUM:
            return [("opencode", self.s.tier2_model)] if self.s.tier2_model else []
        # HARD: use Anthropic directly if a key is set, else serve Claude via OpenCode Zen.
        if not self.s.tier3_model:
            return []
        provider = "anthropic" if self.s.anthropic_api_key else "opencode"
        return [(provider, self.s.tier3_model)]

    def _make(self, provider: str, model_id: str):
        key = (provider, model_id)
        if key in self._cache:
            return self._cache[key]

        if provider in ("openrouter", "opencode"):
            from langchain_openai import ChatOpenAI

            base = (
                self.s.openrouter_base_url
                if provider == "openrouter"
                else self.s.opencode_zen_base_url
            )
            api_key = (
                self.s.openrouter_api_key
                if provider == "openrouter"
                else self.s.opencode_zen_api_key
            )
            model = ChatOpenAI(
                model=model_id, api_key=api_key, base_url=base,
                temperature=0, timeout=90, max_retries=0, max_tokens=2048,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            model = ChatAnthropic(
                model=model_id, api_key=self.s.anthropic_api_key,
                temperature=0, timeout=90, max_retries=0, max_tokens=2048,
            )
        else:  # pragma: no cover - guard
            raise ValueError(f"unknown provider {provider!r}")

        self._cache[key] = model
        return model

    def _candidates(self, tier: Tier, max_tier: Tier) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for t in range(int(tier), int(max_tier) + 1):
            out.extend(self.models_for_tier(Tier(t)))
        return out

    # -- public API ----------------------------------------------------------
    def complete(
        self, system: str, user: str, *, tier: Tier = Tier.CHEAP, max_tier: Tier = Tier.HARD
    ) -> str:
        messages = [("system", system), ("human", user)]
        last_err: Exception | None = None
        for provider, model_id in self._candidates(tier, max_tier):
            try:
                resp = self._make(provider, model_id).invoke(messages)
                return resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:  # noqa: BLE001 - rotate/escalate on any failure
                last_err = e
                log.warning("LLM call failed on %s/%s: %s", provider, model_id, e)
        raise RuntimeError(f"all tiers {tier}..{max_tier} failed") from last_err

    def structured(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        *,
        tier: Tier = Tier.MEDIUM,
        max_tier: Tier = Tier.HARD,
    ) -> BaseModel:
        messages = [("system", system), ("human", user)]
        last_err: Exception | None = None
        for provider, model_id in self._candidates(tier, max_tier):
            try:
                model = self._make(provider, model_id).with_structured_output(schema)
                return model.invoke(messages)
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("structured LLM call failed on %s/%s: %s", provider, model_id, e)
        raise RuntimeError(f"structured: all tiers {tier}..{max_tier} failed") from last_err
