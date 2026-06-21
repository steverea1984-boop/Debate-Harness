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

    # The judge read this stub returns — overridable per subclass so tests can
    # simulate different judge behavior without touching the loop.
    JUDGE_PERCEIVED = "surface"
    JUDGE_CONSENSUS = "disagreement"
    JUDGE_CONFIDENCE = 0.3

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
                "perceived_stage": self.JUDGE_PERCEIVED,
                "consensus_shape": self.JUDGE_CONSENSUS,
                "confidence": self.JUDGE_CONFIDENCE,
                "reason": "stub read",
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


class ResolvingStubProvider(StubProvider):
    """A stub whose judge reads the debate as confidently resolving."""

    JUDGE_PERCEIVED = "resolving"
    JUDGE_CONSENSUS = "productive_stalemate"
    JUDGE_CONFIDENCE = 0.9


class EmptyRefineStubProvider(StubProvider):
    """A stub orchestrator that returns an empty refined prompt (a weak model)."""

    def complete_json(self, system, user, schema, max_tokens):
        data = super().complete_json(system, user, schema, max_tokens)
        if "refined_prompt" in schema.get("properties", {}):
            data["refined_prompt"] = ""  # weak orchestrator emits nothing useful
        return data


class BuildStubProvider(StubProvider):
    """A stub for build mode: seed answers return a base draft; each build turn
    carries the prior working answer forward and appends a marker, so accumulation
    and verbatim pass-through are checkable. Also captures the seed-answer and
    seed-selection prompts (shared class lists) so the non-adversarial seed contract
    can be asserted. complete_json branching is inherited."""

    _MARK = "[Current shared working answer]\n"
    SEED_ANSWER_PROMPTS: list = []
    SEED_SELECT_PROMPTS: list = []

    def complete(self, system, messages, max_tokens):
        content = messages[-1]["content"]
        if self._MARK in content:  # a build turn
            wa = content.split(self._MARK, 1)[1]
            wa = wa.split("\n\n[The other model's last changes]", 1)[0].strip()
            self._n += 1
            return f"{wa}\n[built turn {self._n}]\n=== CHANGES ===\n- added: turn {self._n}"
        BuildStubProvider.SEED_ANSWER_PROMPTS.append(content)
        return "BASE DRAFT."  # seed answer (initial draft)

    def complete_json(self, system, user, schema, max_tokens):
        if "seed_slot" in schema.get("properties", {}):
            BuildStubProvider.SEED_SELECT_PROMPTS.append(user)
        return super().complete_json(system, user, schema, max_tokens)


class RepeatingStubProvider(StubProvider):
    """A stub whose debaters always say the same thing — a circular debate."""

    def complete(self, system, messages, max_tokens):
        return "We should pick the monolith; it is simpler and that point stands."


class OfflineLoopTest(unittest.TestCase):
    def setUp(self):
        # Route all providers to the stub. provider_cls is swappable so a test
        # can choose a different judge behavior.
        self.provider_cls = StubProvider
        self._orig_make = orchestrator.make_provider
        orchestrator.make_provider = lambda provider, model: self.provider_cls(model)
        self.addCleanup(setattr, orchestrator, "make_provider", self._orig_make)

        # Keep log artifacts out of the workspace.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig_logs = logging_utils.LOGS_DIR
        logging_utils.LOGS_DIR = Path(self._tmp.name)
        self.addCleanup(setattr, logging_utils, "LOGS_DIR", self._orig_logs)

    def test_empty_refined_prompt_falls_back_to_raw(self):
        # A weak orchestrator returns an empty refined prompt; the loop must fall
        # back to the raw prompt rather than debate an empty question.
        self.provider_cls = EmptyRefineStubProvider
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 1, 1, 1
        logger = RunLogger(label="empty-refine")
        orchestrator.Orchestrator(cfg, logger).run("Should X or Y?", ask_user=None)
        refine_evt = next(e for e in logger.record["events"] if e["kind"] == "refine")
        self.assertEqual(refine_evt["refined"], "Should X or Y?")

    def test_build_mode_accumulates_and_passes_through(self):
        # Build mode: one growing working answer; final answer = the last working
        # answer verbatim (NOT the present step's re-synthesis).
        self.provider_cls = BuildStubProvider
        cfg = Config()
        cfg.mode = "build"
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 1, 1, 1  # turn_cap 3
        logger = RunLogger(label="build-test")
        result = orchestrator.Orchestrator(cfg, logger).run("Should X or Y?", ask_user=None)

        turns = result.transcript.turns
        self.assertEqual(len(turns), 1 + cfg.turn_cap, "seed + turn_cap")
        self.assertEqual(turns[0].kind, "seed")
        self.assertTrue(all(t.kind == "build" for t in turns[1:]), "debate turns tagged build")

        fa = result.final_answer
        # accumulation: the seed draft survived and each turn added exactly one piece
        self.assertIn("BASE DRAFT.", fa)
        self.assertEqual(fa.count("[built turn"), cfg.turn_cap, "one accumulated addition per turn")

        # pass-through: final answer == the last logged working answer, and is NOT the
        # present step's synthesized text ("stub synthesis").
        build_events = [e for e in logger.record["events"] if e["kind"] == "build_turn"]
        self.assertEqual(len(build_events), cfg.turn_cap)
        self.assertEqual(fa, build_events[-1]["working_answer"], "final answer = last working answer")
        self.assertNotEqual(fa, "stub synthesis", "answer is passed through, not re-synthesized")
        self.assertIn("added: turn", build_events[-1]["changelog"], "changelog parsed")
        self.assertTrue(result.outcome_type, "metadata classification still produced")

    def test_build_mode_seed_is_non_adversarial(self):
        # The seed (turn 0) must already be in build framing, not debate framing.
        self.provider_cls = BuildStubProvider
        BuildStubProvider.SEED_ANSWER_PROMPTS.clear()
        BuildStubProvider.SEED_SELECT_PROMPTS.clear()
        cfg = Config()
        cfg.mode = "build"
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 1, 1, 1
        orchestrator.Orchestrator(cfg, RunLogger(label="build-seed")).run(
            "Should X or Y?", ask_user=None
        )

        seed_answer = " ".join(BuildStubProvider.SEED_ANSWER_PROMPTS).lower()
        self.assertIn("draft & expand", seed_answer)      # build stage label
        self.assertIn("draft", seed_answer)
        self.assertNotIn("opening position", seed_answer)  # debate framing absent
        self.assertNotIn("surface & stress", seed_answer)

        seed_select = " ".join(BuildStubProvider.SEED_SELECT_PROMPTS).lower()
        self.assertIn("build on", seed_select)             # best starting draft
        self.assertNotIn("spark", seed_select)             # not "spark a debate"
        self.assertNotIn("sequential debate", seed_select)

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

    def test_state_based_2to3_reaches_stage3_earlier(self):
        # With the gate ON and a judge that reads "resolving", the loop should
        # advance to stage 3 earlier than the pure timer would, and still stop at
        # the turn cap. Schedule 2/2/1 (turn_cap=5); min_stage2_turns=1.
        self.provider_cls = ResolvingStubProvider
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 2, 2, 1
        cfg.state_based_2to3 = True
        cfg.min_stage2_turns = 1
        cfg.stage_transition_confidence = 0.6

        logger = RunLogger(label="state-test")
        orch = orchestrator.Orchestrator(cfg, logger)
        result = orch.run("Should X or Y?", ask_user=None)

        stages = [t.stage for t in result.transcript.turns]
        # seed(1) + debate [1,1,2,3,3] — stage 3 reached at debate turn 4 vs the
        # timer's turn 5 ([1,1,1,2,2,3]).
        self.assertEqual(stages, [1, 1, 1, 2, 3, 3])
        self.assertEqual(len(result.transcript.turns), 1 + cfg.turn_cap)
        self.assertEqual(result.stop_reason, "turn_cap")

        # A state-driven stage transition was logged.
        kinds = [(e["kind"], e.get("reason")) for e in logger.record["events"]]
        self.assertIn(("stage_transition", "state_advance"), kinds)

    def test_circularity_stop_ends_debate_early(self):
        # Debaters that repeat themselves -> structurally circular. With the gate
        # on, the debate should stop early with stop_reason "circular".
        self.provider_cls = RepeatingStubProvider
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 3, 3, 2  # turn_cap 8
        cfg.enable_circularity_stop = True
        cfg.circularity_min_turns = 4
        cfg.circularity_threshold = 0.6

        logger = RunLogger(label="circ-test")
        orch = orchestrator.Orchestrator(cfg, logger)
        result = orch.run("Monolith or microservices?", ask_user=None)

        self.assertEqual(result.stop_reason, "circular")
        self.assertLess(len(result.transcript.turns), 1 + cfg.turn_cap)
        # Fires at debate turn 4: seed + 4 debate turns = 5 entries.
        self.assertEqual(len(result.transcript.turns), 5)
        kinds = [(e["kind"], e.get("is_circular")) for e in logger.record["events"]]
        self.assertIn(("circularity_read", True), kinds)

    def test_circularity_observe_only_by_default(self):
        # Same repeating debaters, but gate OFF -> still runs to the turn cap,
        # with the circular read logged (observe-only).
        self.provider_cls = RepeatingStubProvider
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 2, 2, 1  # turn_cap 5

        logger = RunLogger(label="circ-observe")
        orch = orchestrator.Orchestrator(cfg, logger)
        result = orch.run("Monolith or microservices?", ask_user=None)

        self.assertEqual(result.stop_reason, "turn_cap")
        self.assertEqual(len(result.transcript.turns), 1 + cfg.turn_cap)
        kinds = [(e["kind"], e.get("is_circular")) for e in logger.record["events"]]
        self.assertIn(("circularity_read", True), kinds)  # observed but not acted on

    def test_stage_schedule_pure(self):
        # Guard config.stage_for_turn independently of the loop.
        cfg = Config()
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 3, 3, 2
        self.assertEqual(cfg.turn_cap, 8)
        seq = [cfg.stage_for_turn(i) for i in range(0, cfg.turn_cap + 1)]
        self.assertEqual(seq, [1, 1, 1, 1, 2, 2, 2, 3, 3])


if __name__ == "__main__":
    unittest.main()
