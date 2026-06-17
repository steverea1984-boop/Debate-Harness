"""Offline unit tests for StageController (spec §7).

No models, no network: the controller is driven with synthetic judge reads and we
assert the stage sequence it produces. Covers default-mode equivalence to the
timer, state-mode advance/backstop/revert, the anti-thrash cap, and the
no-skipping invariant.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Optional

from debate_harness.config import Config
from debate_harness.stages import StageController


@dataclass
class FakeRead:
    perceived_stage: str = "working"
    consensus_shape: str = "disagreement"
    confidence: float = 0.9


def drive(cfg: Config, reads: list[Optional[FakeRead]]):
    """Run a controller over reads; return (stages, transitions, ctrl).

    ``transitions`` collects each non-None ``last_transition`` as it happens, so
    tests can assert the *reason* a stage changed, not just the final state.
    """
    ctrl = StageController(cfg)
    stages = []
    transitions = []
    for turn, read in enumerate(reads, start=1):
        stages.append(ctrl.current_stage(turn))
        ctrl.observe(turn, read)
        if ctrl.last_transition:
            transitions.append(ctrl.last_transition)
    return stages, transitions, ctrl


def _cfg(**overrides) -> Config:
    cfg = Config()
    cfg.state_based_2to3 = True
    cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 2, 3, 2
    cfg.min_stage2_turns = 1
    cfg.stage_transition_confidence = 0.6
    cfg.max_stage_reversals = 1
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


class TimerModeTest(unittest.TestCase):
    """With the gate off, the controller must equal stage_for_turn exactly."""

    def test_matches_stage_for_turn(self):
        for schedule in [(3, 3, 2), (2, 2, 1), (1, 4, 2)]:
            cfg = Config()
            cfg.state_based_2to3 = False
            cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = schedule
            ctrl = StageController(cfg)
            for t in range(1, cfg.turn_cap + 1):
                self.assertEqual(
                    ctrl.current_stage(t), cfg.stage_for_turn(t), f"{schedule} turn {t}"
                )
                ctrl.observe(t, FakeRead())  # no-op in timer mode
                self.assertIsNone(ctrl.last_transition)


class StateModeTest(unittest.TestCase):
    def test_holds_stage2_until_min_then_advances_on_resolving(self):
        cfg = _cfg(min_stage2_turns=2)
        resolving = FakeRead(perceived_stage="resolving", confidence=0.9)
        stages, _t, _ = drive(cfg, [resolving] * 5)
        # stage1(2 turns) -> stage2 held until 2 stage-2 turns -> stage3
        self.assertEqual(stages, [1, 1, 2, 2, 3])

    def test_timer_backstop_without_resolving(self):
        cfg = _cfg()  # min_stage2_turns=1, stage2_turns=3
        working = FakeRead(perceived_stage="working", confidence=0.9)
        stages, transitions, ctrl = drive(cfg, [working] * 6)
        # never "resolved", so 2->3 only by the stage2_turns backstop
        self.assertEqual(stages, [1, 1, 2, 2, 2, 3])
        self.assertIn({"from": 2, "to": 3, "reason": "timer"}, transitions)

    def test_advances_on_terminal_consensus_even_if_perceived_working(self):
        cfg = _cfg()
        read = FakeRead(perceived_stage="working", consensus_shape="productive_stalemate", confidence=0.9)
        stages, _t, _ = drive(cfg, [read] * 4)
        self.assertEqual(stages, [1, 1, 2, 3])

    def test_low_confidence_read_is_ignored(self):
        cfg = _cfg()
        weak = FakeRead(perceived_stage="resolving", confidence=0.3)  # below floor
        stages, _t, _ = drive(cfg, [weak] * 6)
        # falls through to the timer backstop instead of advancing early
        self.assertEqual(stages, [1, 1, 2, 2, 2, 3])

    def test_revert_3_to_2_and_reversal_cap(self):
        cfg = _cfg(stage1_turns=1, stage2_turns=2, min_stage2_turns=1, max_stage_reversals=1)
        res = FakeRead(perceived_stage="resolving", confidence=0.9)
        surf = FakeRead(perceived_stage="surface", confidence=0.9)
        # reach 3, get surfaced back to 2, climb to 3 again, surface again (capped)
        stages, transitions, ctrl = drive(cfg, [res, res, surf, res, res, surf])
        self.assertEqual(stages, [1, 2, 3, 2, 3, 3])
        self.assertEqual(ctrl.reversals, 1)
        reasons = [t["reason"] for t in transitions]
        self.assertIn("state_revert", reasons)
        self.assertEqual(reasons.count("state_revert"), 1)  # capped

    def test_never_skips_a_stage(self):
        cfg = _cfg()
        res = FakeRead(perceived_stage="resolving", confidence=0.99)
        stages, _t, _ = drive(cfg, [res] * 8)
        # 1->2 is turn-based, so even relentless "resolving" cannot jump 1->3
        for a, b in zip(stages, stages[1:]):
            self.assertLessEqual(abs(a - b), 1, f"stage skip in {stages}")
        self.assertNotIn(3, stages[:2])  # stage 3 never appears during stage-1 turns

    def test_none_read_does_not_crash_or_advance(self):
        cfg = _cfg()
        stages, _t, _ = drive(cfg, [None] * 6)
        self.assertEqual(stages, [1, 1, 2, 2, 2, 3])  # timer backstop only

    def test_malformed_read_does_not_crash(self):
        # A read missing fields, or with a non-numeric confidence, must not raise
        # (spec Error Behavior) — it's treated as "no signal" (timer backstop).
        cfg = _cfg()
        bad = [
            object(),  # no fields at all
            FakeRead(perceived_stage="resolving", confidence=None),  # None confidence
            object(),
            FakeRead(perceived_stage="resolving", confidence=None),
            object(),
            object(),
        ]
        stages, _t, _ = drive(cfg, bad)
        self.assertEqual(stages, [1, 1, 2, 2, 2, 3])


if __name__ == "__main__":
    unittest.main()
