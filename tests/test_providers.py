"""Offline tests for the provider layer.

Guards the OpenAI call contract without touching the network: the chat
completion must be requested with ``max_completion_tokens`` (the parameter the
GPT-5 series requires; ``max_tokens`` is rejected with a 400 and is deprecated
for chat completions generally). A fake client captures the kwargs.

Run locally with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

from debate_harness.providers import OpenAIProvider


class _CapturingCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        msg = SimpleNamespace(content="hello")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_CapturingCompletions())


class OpenAIProviderContractTest(unittest.TestCase):
    def setUp(self):
        # OpenAI() reads the key from the env at construction (no network call).
        self._had_key = "OPENAI_API_KEY" in os.environ
        os.environ.setdefault("OPENAI_API_KEY", "sk-test-offline")
        self.addCleanup(self._restore_key)

    def _restore_key(self):
        if not self._had_key:
            os.environ.pop("OPENAI_API_KEY", None)

    def test_complete_uses_max_completion_tokens(self):
        provider = OpenAIProvider("gpt-5.5")
        provider._client = _FakeClient()  # swap real client for the capturing fake

        out = provider.complete("sys", [{"role": "user", "content": "hi"}], max_tokens=256)

        self.assertEqual(out, "hello")
        sent = provider._client.chat.completions.kwargs
        self.assertEqual(sent["max_completion_tokens"], 256)
        self.assertNotIn("max_tokens", sent, "GPT-5 rejects max_tokens")
        self.assertEqual(sent["model"], "gpt-5.5")
        self.assertEqual(sent["messages"][0], {"role": "system", "content": "sys"})


if __name__ == "__main__":
    unittest.main()
