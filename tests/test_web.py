"""Offline tests for the web UI's dependency-free core (models + runs).

Imports only `debate_harness.models` and `debate_harness.runs` — NOT `web` (which
needs FastAPI). No SDKs, no network, no real debates: these guard the catalog,
request->Config mapping, and on-disk run summarisation. CI installs no deps.

Run locally with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from debate_harness import runs
from debate_harness.models import curated_model_dicts

_ENV_KEYS = [
    "SLOT_A_PROVIDER", "SLOT_A_MODEL", "SLOT_B_PROVIDER", "SLOT_B_MODEL",
    "ORCHESTRATOR_PROVIDER", "ORCHESTRATOR_MODEL", "JUDGE_PROVIDER", "JUDGE_MODEL",
    "ANTHROPIC_MODEL", "OPENAI_MODEL",
]


class CatalogTest(unittest.TestCase):
    def test_catalog_shape_and_values(self):
        cat = curated_model_dicts()
        self.assertGreaterEqual(len(cat), 6)
        tiers = {m["tier"] for m in cat}
        self.assertIn("value", tiers)
        self.assertIn("premium", tiers)
        for m in cat:
            for key in ("value", "label", "vendor", "tier", "price_in", "price_out", "referee_ok"):
                self.assertIn(key, m)
            provider, sep, model = m["value"].partition(":")
            self.assertTrue(sep and provider and model, m["value"])  # parseable endpoint
        # Catalog distinguishes referee-safe models from debater-only ones.
        self.assertTrue(any(m["referee_ok"] for m in cat))
        self.assertTrue(any(not m["referee_ok"] for m in cat))


class ParseEndpointTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(runs.parse_endpoint("openrouter:anthropic/claude-3.5-haiku"),
                         ("openrouter", "anthropic/claude-3.5-haiku"))

    def test_malformed(self):
        for bad in ("nocolon", ":model", "provider:", ""):
            with self.assertRaises(ValueError):
                runs.parse_endpoint(bad)


class BuildConfigTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_defaults_when_empty(self):
        c = runs.build_config({"prompt": "x"})
        self.assertEqual((c.slot_a.provider, c.slot_a.model), ("anthropic", "claude-opus-4-8"))
        self.assertFalse(c.clarify)  # web never blocks on clarifying questions

    def test_overrides_and_judge_follows_orchestrator(self):
        c = runs.build_config({
            "slot_a": "openrouter:meta-llama/llama-3.3-70b-instruct",
            "orchestrator": "openrouter:google/gemini-2.5-flash",
            "stages": [1, 1, 1],
            "judge_stop": True,
        })
        self.assertEqual((c.slot_a.provider, c.slot_a.model), ("openrouter", "meta-llama/llama-3.3-70b-instruct"))
        self.assertEqual((c.stage1_turns, c.stage2_turns, c.stage3_turns), (1, 1, 1))
        self.assertTrue(c.enable_judge_stop)
        # judge unspecified -> mirrors the (overridden) orchestrator
        self.assertEqual((c.effective_judge_provider, c.effective_judge_model),
                         ("openrouter", "google/gemini-2.5-flash"))

    def test_independent_judge(self):
        c = runs.build_config({"judge": "openrouter:deepseek/deepseek-chat-v3-0324"})
        self.assertEqual((c.effective_judge_provider, c.effective_judge_model),
                         ("openrouter", "deepseek/deepseek-chat-v3-0324"))

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            runs.build_config({"slot_a": "no-colon"})
        with self.assertRaises(ValueError):
            runs.build_config({"stages": [1, 2]})

    def test_start_requires_prompt(self):
        with self.assertRaises(ValueError):
            runs.start_debate({"prompt": "   "})


class SummariseRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig = runs.LOGS_DIR
        runs.LOGS_DIR = Path(self._tmp.name)
        self.addCleanup(lambda: setattr(runs, "LOGS_DIR", self._orig))

    def _write_run(self, name, record):
        d = Path(self._tmp.name) / name
        d.mkdir()
        (d / "run.json").write_text(json.dumps(record), encoding="utf-8")
        (d / "transcript.md").write_text("# Debate\n\nbody", encoding="utf-8")
        return d

    def test_summary_and_list_and_load(self):
        rec = {
            "started_at": "20260618-101010",
            "raw_prompt": "Monolith or microservices?",
            "config": {
                "slot_a": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct"},
                "slot_b": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
                "orchestrator_provider": "openrouter", "orchestrator_model": "openai/gpt-4o-mini",
                "judge_provider": "openrouter", "judge_model": "google/gemini-2.5-flash",
            },
            "events": [{"kind": "judge_read", "consensus_shape": "disagreement", "confidence": 0.5}],
            "finished_at": "20260618-101500",
            "summary": {"outcome_type": "genuine_consensus", "stop_reason": "turn_cap", "turns": 6},
        }
        self._write_run("20260618-101010-monolith", rec)

        runs_list = runs.list_runs()
        self.assertEqual(len(runs_list), 1)
        s = runs_list[0]
        self.assertEqual(s["status"], "done")          # finished_at present, not error
        self.assertEqual(s["outcome"], "genuine_consensus")
        self.assertEqual(s["models"]["judge"], "openrouter:google/gemini-2.5-flash")

        full = runs.load_run("20260618-101010-monolith")
        self.assertEqual(full["status"], "done")
        self.assertIn("body", full["transcript"])

    def test_unfinished_run_is_unknown(self):
        self._write_run("20260618-090000-wip", {"raw_prompt": "x", "config": {}, "events": []})
        self.assertEqual(runs.list_runs()[0]["status"], "unknown")  # no finished_at, not in-process


if __name__ == "__main__":
    unittest.main()
