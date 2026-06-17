"""Stage transition control (spec §7).

`StageController` owns the one decision "which stage is this turn in?" — kept out
of the main loop so it can be unit-tested without any model calls. It is
**LLM-free**: it does no reasoning itself, it only reacts to the judge's read
(produced elsewhere).

Two modes, selected by ``Config.state_based_2to3``:

- **timer** (default): the stage is a pure function of the turn index, identical
  to ``Config.stage_for_turn`` — i.e. today's behavior, unchanged.
- **state**: the 1→2 boundary stays turn-based, but the 2→3 boundary is driven by
  the judge's read ("resolving" / a terminal consensus shape => advance), with the
  spec's safeguards: a minimum number of stage-2 turns first, a turn-based
  backstop so stage 3 still happens if the judge never signals, and a bounded,
  reversible step *back* to stage 2 if a later read shows the models are still far
  apart.

The controller consumes a *duck-typed* read: any object exposing
``perceived_stage``, ``consensus_shape``, and ``confidence`` (``judge.JudgeRead``
qualifies). It deliberately does not import ``judge`` — that keeps it decoupled
and trivially testable with synthetic reads.
"""

from __future__ import annotations

from typing import Any, Optional


# Consensus shapes that mean "the surfaced disagreements are resolved enough to
# move toward closing" — mirrors judge.TERMINAL_SHAPES minus "circular" (a stuck
# debate is not a resolved one).
_RESOLVED_CONSENSUS = {"genuine_consensus", "productive_stalemate"}


def _confident(read: Any, confidence_floor: float) -> bool:
    """True only for a read with a usable numeric confidence at/above the floor.

    Fully duck-typed and exception-free (spec Error Behavior): a None read, a
    missing/None confidence, or a non-numeric confidence all return False rather
    than raising.
    """
    if read is None:
        return False
    conf = getattr(read, "confidence", None)
    if not isinstance(conf, (int, float)):
        return False
    return conf >= confidence_floor


def _is_resolved(read: Any, confidence_floor: float) -> bool:
    """The judge reads the debate as having worked through its disagreements."""
    if not _confident(read, confidence_floor):
        return False
    return (
        getattr(read, "perceived_stage", None) == "resolving"
        or getattr(read, "consensus_shape", None) in _RESOLVED_CONSENSUS
    )


def _is_far_apart(read: Any, confidence_floor: float) -> bool:
    """The judge reads the debate as clearly still surfacing problems.

    Conservative on purpose: only a confident "surface" read counts (the §7
    'premature cool-down should self-correct' case). "working" + disagreement is
    the *normal* stage-2 state and must not trigger a reversal.
    """
    if not _confident(read, confidence_floor):
        return False
    return getattr(read, "perceived_stage", None) == "surface"


class StageController:
    def __init__(self, config):
        self.cfg = config
        self.state_mode: bool = bool(getattr(config, "state_based_2to3", False))
        self.stage: int = 1
        self.turns_in_stage: int = 0
        self.reversals: int = 0
        # Set to {"from", "to", "reason"} on the turn a transition happens, else
        # None. The loop reads this to log "every stage decision" (spec §12).
        self.last_transition: Optional[dict[str, Any]] = None

    def current_stage(self, debate_turn: int) -> int:
        """The stage to run ``debate_turn`` in."""
        if not self.state_mode:
            return self.cfg.stage_for_turn(debate_turn)
        return self.stage

    def observe(self, debate_turn: int, read: Any) -> None:
        """Update internal stage for the *next* turn, given this turn's read."""
        self.last_transition = None
        if not self.state_mode:
            return

        self.turns_in_stage += 1
        cfg = self.cfg

        if self.stage == 1:
            # 1->2 stays turn-based (spec §7).
            if self.turns_in_stage >= cfg.stage1_turns:
                self._transition(2, "timer")
        elif self.stage == 2:
            if (
                self.turns_in_stage >= cfg.min_stage2_turns
                and _is_resolved(read, cfg.stage_transition_confidence)
            ):
                self._transition(3, "state_advance")
            elif self.turns_in_stage >= cfg.stage2_turns:
                # Backstop: stage 3 still happens even if the judge never signals.
                self._transition(3, "timer")
        elif self.stage == 3:
            if (
                self.reversals < cfg.max_stage_reversals
                and _is_far_apart(read, cfg.stage_transition_confidence)
            ):
                self.reversals += 1
                self._transition(2, "state_revert")

    def _transition(self, to_stage: int, reason: str) -> None:
        self.last_transition = {"from": self.stage, "to": to_stage, "reason": reason}
        self.stage = to_stage
        self.turns_in_stage = 0
