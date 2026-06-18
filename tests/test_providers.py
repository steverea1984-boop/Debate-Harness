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


if __name__ == "__main__":
    unittest.main()
