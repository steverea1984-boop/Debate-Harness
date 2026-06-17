"""Offline control-flow test for the debate harness.

Drives the full orchestrator loop (refine -> seed -> staged alternation ->
observe-only judge after every turn -> present, with logging) using a stub
provider, so it runs in CI with no API keys and no network. It guards the
control-flow invariants: turn count, the stage schedule, speaker alternation, and
that log artifacts are written.

The seam: monkeypatch ``debate_harness.orchestrator.make_provider`` so the real
``Orchestrator``/``Debater``/``Judge`` construction path runs but every provider
is a stub. Run locally with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from debate_harness import config as config_mod
from debate_harness import logging_utils, orchestrator
from debate_harness.config import Config
from debate_harness.logging_utils import RunLogger
from debate_harness.providers import Provider


class StubProvider(Provider):
    """Implements the whole Provider interface with deterministic, offline output.

    One stub serves all three call sites (orchestrator/judge, slot A, slot B):
    ``complete`` returns debater/seed text; ``complete_json`` returns a valid
    object for each orchestrator/judge schema, branching on its property names.
    """

    vendor = "stub"

    def __init__(self, model: str):
        super().__init__(model)
        self._n = 0

    def complete(self, system, messages, max_tokens):
        self._n += 1
        return f"[stub turn #{self._n}]"

    def complete_json(self, system, user, schema, max_tokens):
        props = schema.get("properties", {})
        if "refined_prompt" in props:
            return {
                "needs_clarification": False,
                "clarifying_questions": [],
                "refined_prompt": "REFINED: stub",
            }
        if "seed_slot" in props:
            return {"seed_slot": "A", "criteria": "clarity", "reasoning": "A is clearer"}
        if "perceived_stage" in props:  # judge
            return {
                "perceived_stage": "surface",
                "consensus_shape": "disagreement",
                "confidence": 0.3,
                "reason": "still arguing",
                "should_stop": False,
            }
        if "request_elaboration" in props:
            return {"request_elaboration": False, "instruction": "", "reason": ""}
        if "outcome_type" in props:  # present
            return {
                "outcome_type": "turn_cap_no_convergence",
                "final_answer": "stub synthesis",
                "residual_disagreement": "axis X",
                "note_to_user": "did not converge",
            }
        raise AssertionError(f"unexpected schema in complete_json: {sorted(props)}")


class OfflineLoopTest(unittest.TestCase):
    def setUp(self):
        # Route all providers to the stub.
        self._orig_make = orchestrator.make_provider
        orchestrator.make_provider = lambda provider, model: StubProvider(model)
        self.addCleanup(setattr, orchestrator, "make_provider", self._orig_make)

        # Keep log artifacts out of the workspace.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig_logs = logging_utils.LOGS_DIR
        logging_utils.LOGS_DIR = Path(self._tmp.name)
        self.addCleanup(setattr, logging_utils, "LOGS_DIR", self._orig_logs)

    def test_full_loop_invariants(self):
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 2, 2, 1
        self.assertEqual(cfg.turn_cap, 5)

        logger = RunLogger(label="offline-test")
        orch = orchestrator.Orchestrator(cfg, logger)
        result = orch.run("Should X or Y?", ask_user=None)

        turns = result.transcript.turns

        # Turn count = seed + turn_cap.
        self.assertEqual(len(turns), 1 + cfg.turn_cap, "seed + turn_cap turns")

        # Stage schedule: seed=1, then per config.stage_for_turn.
        expected_stages = [1] + [cfg.stage_for_turn(i) for i in range(1, cfg.turn_cap + 1)]
        self.assertEqual([t.stage for t in turns], expected_stages)
        self.assertEqual(expected_stages, [1, 1, 1, 2, 2, 3])

        # Speakers: seed slot (A here), then strict alternation starting with the
        # non-seeding slot.
        seed_slot = turns[0].speaker_slot
        other = "B" if seed_slot == "A" else "A"
        expected_speakers = [seed_slot]
        nxt = other
        for _ in range(cfg.turn_cap):
            expected_speakers.append(nxt)
            nxt = "B" if nxt == "A" else "A"
        self.assertEqual([t.speaker_slot for t in turns], expected_speakers)
        # No debater ever speaks twice in a row.
        for a, b in zip(turns, turns[1:]):
            self.assertNotEqual(a.speaker_slot, b.speaker_slot)

        # Seed is turn 0 and tagged as the seed.
        self.assertEqual(turns[0].index, 0)
        self.assertEqual(turns[0].kind, "seed")

        # A terminal result was produced.
        self.assertTrue(result.outcome_type)
        self.assertEqual(result.stop_reason, "turn_cap")

        # Log artifacts written.
        self.assertTrue((logger.dir / "run.json").exists(), "run.json written")
        self.assertTrue((logger.dir / "transcript.md").exists(), "transcript.md written")

    def test_stage_schedule_pure(self):
        # Guard config.stage_for_turn independently of the loop.
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 3, 3, 2
        self.assertEqual(cfg.turn_cap, 8)
        seq = [cfg.stage_for_turn(i) for i in range(0, cfg.turn_cap + 1)]
        self.assertEqual(seq, [1, 1, 1, 1, 2, 2, 2, 3, 3])


if __name__ == "__main__":
    unittest.main()
