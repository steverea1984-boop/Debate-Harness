"""Model-provider abstraction.

Both debater slots, the orchestrator, and the judge call models through a single
small interface so the rest of the harness never has to care whether a turn is
coming from Anthropic or OpenAI. A "message" is a plain dict
``{"role": "user"|"assistant", "content": str}``; the system prompt is passed
separately and each provider places it where its API expects.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class ProviderError(RuntimeError):
    pass


class Provider(ABC):
    """A thin wrapper around one model endpoint."""

    def __init__(self, model: str):
        self.model = model

    @property
    def label(self) -> str:
        return f"{self.vendor}:{self.model}"

    @property
    @abstractmethod
    def vendor(self) -> str: ...

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> str:
        """Return the assistant's text response for a system prompt + thread."""

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> dict[str, Any]:
        """Return a parsed JSON object constrained to ``schema``.

        Default implementation asks for JSON in-prompt and extracts the object.
        Providers with native structured-output support override this.
        """
        instruction = (
            user
            + "\n\nRespond with a single JSON object matching this schema "
            + "(no prose, no code fences):\n"
            + json.dumps(schema)
        )
        text = self.complete(system, [{"role": "user", "content": instruction}], max_tokens)
        return _extract_json(text)


class AnthropicProvider(Provider):
    vendor = "anthropic"

    def __init__(self, model: str):
        super().__init__(model)
        import anthropic  # imported lazily so the OpenAI-only path doesn't need it

        self._client = anthropic.Anthropic()

    def complete(self, system, messages, max_tokens):
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def complete_json(self, system, user, schema, max_tokens):
        # Native structured output: constrain the response to the schema.
        # (No thinking param here — keep these judgment calls fast and cheap.)
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": schema,
                }
            },
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return _extract_json(text)


class OpenAIProvider(Provider):
    vendor = "openai"

    def __init__(self, model: str):
        super().__init__(model)
        from openai import OpenAI  # lazy import

        self._client = OpenAI()

    def complete(self, system, messages, max_tokens):
        full = [{"role": "system", "content": system}, *messages]
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=full,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()


def make_provider(provider: str, model: str) -> Provider:
    provider = provider.lower()
    if provider == "anthropic":
        return AnthropicProvider(model)
    if provider == "openai":
        return OpenAIProvider(model)
    raise ProviderError(f"Unknown provider: {provider!r}")


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object out of a model response."""
    text = text.strip()
    # Strip a ```json ... ``` fence if present.
    if text.startswith("```"):
        text = text.strip("`")
        text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ProviderError(f"Could not parse JSON from model response:\n{text[:500]}")
