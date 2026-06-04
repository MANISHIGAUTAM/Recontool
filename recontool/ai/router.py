"""Tiered model router — use the cheapest model that can do the job.

  - LIGHT model: routine triage, phase notes, keep/drop planning, classification.
  - HEAVY model: only for complex synthesis (final narrative, anomaly reasoning).

Token-minimisation is enforced structurally:
  - a hard per-scan call budget (settings.ai_max_calls),
  - callers send COMPACT summaries (counts + a few samples), never raw dumps,
  - low max_tokens on responses,
  - graceful no-op when AI isn't configured (returns None -> heuristic fallback).

Works against any OpenAI-compatible endpoint (OpenAI, or local Ollama/vLLM).
"""
from __future__ import annotations

import json
from typing import Literal

from recontool.config import settings

Tier = Literal["light", "heavy"]


class ModelRouter:
    def __init__(self):
        self.enabled = settings.ai_enabled
        self.calls_made = 0
        self.budget = settings.ai_max_calls  # 0 = unlimited
        self._client = None
        if self.enabled:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    base_url=settings.ai_base_url, api_key=settings.ai_api_key
                )
            except Exception:  # noqa: BLE001 — library missing or bad config
                self.enabled = False

    def _model_for(self, tier: Tier) -> str:
        return settings.ai_model_heavy if tier == "heavy" else settings.ai_model_light

    def _budget_left(self) -> bool:
        return self.budget == 0 or self.calls_made < self.budget

    async def decide_json(
        self, system: str, payload: dict, tier: Tier = "light", max_tokens: int = 200
    ) -> dict | None:
        """Ask the model for a STRICT JSON decision. Returns None if unavailable
        or budget exhausted (caller must have a heuristic fallback)."""
        text = await self.chat(
            system + "\nRespond with ONLY compact JSON.",
            json.dumps(payload, separators=(",", ":")),
            tier=tier, max_tokens=max_tokens,
        )
        if not text:
            return None
        try:
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start : end + 1])
        except Exception:  # noqa: BLE001
            return None

    async def chat(
        self, system: str, user: str, tier: Tier = "light", max_tokens: int = 256
    ) -> str | None:
        if not self.enabled or self._client is None or not self._budget_left():
            return None
        try:
            self.calls_made += 1
            resp = await self._client.chat.completions.create(
                model=self._model_for(tier),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            return resp.choices[0].message.content
        except Exception:  # noqa: BLE001
            return None

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "calls_made": self.calls_made,
            "budget": self.budget,
            "light_model": settings.ai_model_light,
            "heavy_model": settings.ai_model_heavy,
        }
