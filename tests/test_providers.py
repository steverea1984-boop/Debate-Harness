"""Offline tests for the provider layer.

Guards the OpenAI call contract without touching the network *or requiring the
openai SDK to be installed* (CI runs with no dependencies — stub providers only).
A fake ``openai`` module is injected into ``sys.modules`` so the provider's lazy
``from openai import OpenAI`` resolves to a capturing fake, letting us assert the
request uses ``max_completion_tokens`` (required by the GPT-5 series; ``max_tokens``
is rejected with a 400 and is deprecated for chat completions generally).

Run locally with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from types import SimpleNamespace


class _CapturingCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        msg = SimpleNamespace(content="hello")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs  # capture base_url / api_key wiring
        self.chat = SimpleNamespace(completions=_CapturingCompletions())


class OpenAIProviderContractTest(unittest.TestCase):
    def setUp(self):
        # Inject a fake `openai` module so OpenAIProvider's lazy import resolves
        # with no SDK installed and no network. Restored after the test.
        self._orig = sys.modules.get("openai")
        fake = types.ModuleType("openai")
        fake.OpenAI = _FakeClient
        sys.modules["openai"] = fake
        self.addCleanup(self._restore)

    def _restore(self):
        if self._orig is not None:
            sys.modules["openai"] = self._orig
        else:
            sys.modules.pop("openai", None)

    def test_complete_uses_max_completion_tokens(self):
        from debate_harness.providers import OpenAIProvider

        provider = OpenAIProvider("gpt-5.5")  # _client is our _FakeClient
        out = provider.complete("sys", [{"role": "user", "content": "hi"}], max_tokens=256)

        self.assertEqual(out, "hello")
        sent = provider._client.chat.completions.kwargs
        self.assertEqual(sent["max_completion_tokens"], 256)
        self.assertNotIn("max_tokens", sent, "GPT-5 rejects max_tokens")
        self.assertEqual(sent["model"], "gpt-5.5")
        self.assertEqual(sent["messages"][0], {"role": "system", "content": "sys"})


class OpenRouterProviderContractTest(unittest.TestCase):
    def setUp(self):
        self._orig = sys.modules.get("openai")
        fake = types.ModuleType("openai")
        fake.OpenAI = _FakeClient
        sys.modules["openai"] = fake
        self._had_key = "OPENROUTER_API_KEY" in os.environ
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        self.addCleanup(self._restore)

    def _restore(self):
        if self._orig is not None:
            sys.modules["openai"] = self._orig
        else:
            sys.modules.pop("openai", None)
        if not self._had_key:
            os.environ.pop("OPENROUTER_API_KEY", None)

    def test_wiring_and_max_tokens(self):
        from debate_harness.providers import OpenRouterProvider

        provider = OpenRouterProvider("anthropic/claude-3.5-haiku")
        # Client wired to OpenRouter base URL with the OpenRouter key.
        self.assertEqual(
            provider._client.init_kwargs["base_url"], "https://openrouter.ai/api/v1"
        )
        self.assertEqual(provider._client.init_kwargs["api_key"], "sk-or-test")

        out = provider.complete("sys", [{"role": "user", "content": "hi"}], max_tokens=128)
        self.assertEqual(out, "hello")
        sent = provider._client.chat.completions.kwargs
        # OpenRouter uses max_tokens, NOT max_completion_tokens.
        self.assertEqual(sent["max_tokens"], 128)
        self.assertNotIn("max_completion_tokens", sent)
        self.assertEqual(sent["model"], "anthropic/claude-3.5-haiku")

    def test_missing_key_raises(self):
        from debate_harness.providers import OpenRouterProvider, ProviderError

        os.environ.pop("OPENROUTER_API_KEY", None)
        with self.assertRaises(ProviderError):
            OpenRouterProvider("anthropic/claude-3.5-haiku")


class MakeProviderTest(unittest.TestCase):
    def setUp(self):
        self._orig = sys.modules.get("openai")
        fake = types.ModuleType("openai")
        fake.OpenAI = _FakeClient
        sys.modules["openai"] = fake
        os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")
        self.addCleanup(lambda: sys.modules.__setitem__("openai", self._orig)
                        if self._orig is not None else sys.modules.pop("openai", None))

    def test_dispatch_openrouter(self):
        from debate_harness.providers import make_provider, OpenRouterProvider, ProviderError

        self.assertIsInstance(make_provider("openrouter", "x/y"), OpenRouterProvider)
        with self.assertRaises(ProviderError):
            make_provider("nope", "m")


if __name__ == "__main__":
    unittest.main()
