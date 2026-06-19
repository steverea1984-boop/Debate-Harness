"""Curated model catalog for the UI / experiments.

A hand-picked set of **mid-tier, good-value** models (not the cheapest, not the
flagships) spanning vendors, reachable through one OpenRouter key, plus the direct
"premium" defaults. Prices are approximate USD per million tokens (input/output)
from OpenRouter at the time of writing and are for rough guidance only — they
drift, so treat them as labels, not invoices.

Each entry's ``value`` is the ``provider:model`` string the CLI/config accept.

``referee_ok`` marks whether a model is reliable in the demanding **orchestrator /
judge** roles (which must emit structured JSON: refine, seed-selection, the
per-turn judge read, present). A 2026-06-18 sweep ran each model as orchestrator
on a fixed debate; those that cleanly refined the prompt are referee-safe, while
the rest returned an empty refine (and historically truncated/garbled JSON) — they
still make fine *debaters*, so they stay in the catalog but the UI only offers
referee-safe models for the orchestrator/judge pickers. n=1 per model; preliminary.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ModelOption:
    value: str          # "provider:model" (e.g. "openrouter:google/gemini-2.5-flash")
    label: str          # human label for the picker
    vendor: str         # anthropic | openai | google | deepseek | meta | qwen | mistral
    tier: str           # "premium" | "strong-mid" | "value"
    price_in: float     # approx $/Mtok input
    price_out: float    # approx $/Mtok output
    referee_ok: bool    # reliable as orchestrator/judge (else: good debater only)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Mid-tier value models via OpenRouter, ordered cheap -> pricier within reason.
_MID = [
    ModelOption("openrouter:meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", "meta", "value", 0.10, 0.32, True),
    ModelOption("openrouter:deepseek/deepseek-chat-v3-0324", "DeepSeek V3 (0324)", "deepseek", "value", 0.20, 0.77, True),
    ModelOption("openrouter:qwen/qwen-2.5-72b-instruct", "Qwen2.5 72B", "qwen", "value", 0.36, 0.40, True),
    ModelOption("openrouter:openai/gpt-4.1-mini", "GPT-4.1 mini", "openai", "value", 0.40, 1.60, True),
    ModelOption("openrouter:openai/gpt-4o", "GPT-4o", "openai", "strong-mid", 2.50, 10.00, True),
    ModelOption("openrouter:anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6", "anthropic", "strong-mid", 3.00, 15.00, True),
    # Good debaters, but unreliable as orchestrator/judge (empty refine / JSON issues):
    ModelOption("openrouter:google/gemini-2.5-flash", "Gemini 2.5 Flash", "google", "value", 0.30, 2.50, False),
    ModelOption("openrouter:mistralai/mistral-medium-3.1", "Mistral Medium 3.1", "mistral", "value", 0.40, 2.00, False),
    ModelOption("openrouter:anthropic/claude-3.5-haiku", "Claude 3.5 Haiku", "anthropic", "value", 0.80, 4.00, False),
    ModelOption("openrouter:google/gemini-2.5-pro", "Gemini 2.5 Pro", "google", "strong-mid", 1.25, 10.00, False),
]

# The existing direct-API defaults, shown as the premium tier for comparison.
_PREMIUM = [
    ModelOption("anthropic:claude-opus-4-8", "Claude Opus 4.8 (direct)", "anthropic", "premium", 0.0, 0.0, True),
    ModelOption("openai:gpt-5.5", "GPT-5.5 (direct)", "openai", "premium", 0.0, 0.0, True),
]

CURATED_MODELS: list[ModelOption] = _MID + _PREMIUM


def curated_model_dicts() -> list[dict[str, Any]]:
    """JSON-serializable catalog for the API / UI."""
    return [m.to_dict() for m in CURATED_MODELS]
