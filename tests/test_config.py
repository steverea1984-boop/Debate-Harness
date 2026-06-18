"""Offline tests for per-role model selection (config + CLI wiring).

No SDKs, no network: these only exercise config resolution and argument parsing.
A `.env` on disk would otherwise leak `OPENAI_MODEL=...` etc. into os.environ via
python-dotenv at import time, so each test clears the relevant keys first to stay
deterministic (mirrors CI, which has no `.env`).

Run locally with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import unittest

from debate_harness.config import Config

_ENV_KEYS = [
    "SLOT_A_PROVIDER", "SLOT_A_MODEL", "SLOT_B_PROVIDER", "SLOT_B_MODEL",
    "ORCHESTRATOR_PROVIDER", "ORCHESTRATOR_MODEL", "JUDGE_PROVIDER", "JUDGE_MODEL",
    "ANTHROPIC_MODEL", "OPENAI_MODEL",
]


class _CleanEnv(unittest.TestCase):
    """Base: snapshot + clear the model env vars, restore on teardown."""

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def setenv(self, **kv):
        for k, v in kv.items():
            os.environ[k] = v


class DefaultParityTest(_CleanEnv):
    def test_defaults_match_current_behavior(self):
        c = Config()
        self.assertEqual((c.slot_a.provider, c.slot_a.model), ("anthropic", "claude-opus-4-8"))
        self.assertEqual((c.slot_b.provider, c.slot_b.model), ("openai", "gpt-4o"))
        self.assertEqual((c.orchestrator_provider, c.orchestrator_model), ("anthropic", "claude-opus-4-8"))
        # Judge mirrors the orchestrator when unset.
        self.assertEqual((c.effective_judge_provider, c.effective_judge_model), ("anthropic", "claude-opus-4-8"))
        self.assertIsNone(c.judge_provider)

    def test_to_dict_records_resolved_judge(self):
        c = Config()
        d = c.to_dict()
        self.assertEqual(d["judge_provider"], "anthropic")
        self.assertEqual(d["judge_model"], "claude-opus-4-8")


class EnvOverrideTest(_CleanEnv):
    def test_per_role_env_vars(self):
        self.setenv(
            SLOT_A_PROVIDER="openrouter", SLOT_A_MODEL="x/y",
            JUDGE_PROVIDER="openrouter", JUDGE_MODEL="anthropic/claude-3.5-haiku",
        )
        c = Config()
        self.assertEqual((c.slot_a.provider, c.slot_a.model), ("openrouter", "x/y"))
        self.assertEqual((c.effective_judge_provider, c.effective_judge_model),
                         ("openrouter", "anthropic/claude-3.5-haiku"))

    def test_legacy_model_var_still_fallback(self):
        self.setenv(OPENAI_MODEL="gpt-5.5")  # no SLOT_B_MODEL set
        self.assertEqual(Config().slot_b.model, "gpt-5.5")


class CliOverrideTest(_CleanEnv):
    def _cfg(self, argv):
        from debate_harness.cli import build_parser, _build_config
        return _build_config(build_parser().parse_args(argv))

    def test_endpoint_flags_override(self):
        c = self._cfg(["--orchestrator", "openrouter:anthropic/claude-3.5-haiku", "p"])
        self.assertEqual((c.orchestrator_provider, c.orchestrator_model),
                         ("openrouter", "anthropic/claude-3.5-haiku"))
        # Judge unset on the CLI -> follows the (CLI-overridden) orchestrator.
        self.assertEqual((c.effective_judge_provider, c.effective_judge_model),
                         ("openrouter", "anthropic/claude-3.5-haiku"))

    def test_judge_independent_of_orchestrator(self):
        c = self._cfg(["--judge", "openrouter:meta-llama/llama-3.3-70b-instruct", "p"])
        self.assertEqual((c.effective_judge_provider, c.effective_judge_model),
                         ("openrouter", "meta-llama/llama-3.3-70b-instruct"))
        # Orchestrator stays at default.
        self.assertEqual(c.orchestrator_provider, "anthropic")

    def test_malformed_endpoint_errors(self):
        from debate_harness.cli import build_parser
        with self.assertRaises(SystemExit):  # argparse exits on a bad value
            build_parser().parse_args(["--judge", "no-colon-here", "p"])


if __name__ == "__main__":
    unittest.main()
