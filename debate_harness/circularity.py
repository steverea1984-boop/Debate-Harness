"""Structural circularity detection (spec §10).

A cheap, **LLM-free** check for the "they're just restating themselves" failure
mode: after each turn it compares a debater's latest turn against that same
debater's turn two back (and the other debater's likewise), using plain
standard-library text similarity. No model call, no network — deterministic and
free, so it can run every turn and be unit-tested with synthetic transcripts.

Like ``StageController``, it only *reads*; whether to act on a circular verdict is
the orchestrator's decision (gated by ``Config.enable_circularity_stop``, off by
default — observe-only).

Turns strictly alternate speakers, so ``turns[-1]`` and ``turns[-3]`` are the same
debater, as are ``turns[-2]`` and ``turns[-4]``. "The last two exchanges restate
the previous two" (§10) is exactly: both of those same-speaker pairs are near-
restatements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import only for typing; avoids any runtime import coupling
    from .transcript import Transcript


@dataclass
class CircularityRead:
    evaluated: bool  # were there enough turns to judge?
    is_circular: bool
    threshold: float
    pair_scores: list[float] = field(default_factory=list)  # [sim(-1,-3), sim(-2,-4)]


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _similar(a: str, b: str) -> float:
    """Case/whitespace-insensitive word-level similarity in [0.0, 1.0]."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        # Two empty turns are degenerate, not "circular".
        return 0.0
    return SequenceMatcher(None, ta, tb, autojunk=False).ratio()


class CircularityDetector:
    def __init__(self, config):
        self.cfg = config

    def read(self, transcript: "Transcript") -> CircularityRead:
        """Evaluate the most recent turn against the same-speaker history."""
        cfg = self.cfg
        turns = transcript.turns
        # Need four turns, and enough debate turns to not fire prematurely.
        if len(turns) < 4 or turns[-1].index < cfg.circularity_min_turns:
            return CircularityRead(
                evaluated=False, is_circular=False, threshold=cfg.circularity_threshold
            )
        s1 = _similar(turns[-1].text, turns[-3].text)
        s2 = _similar(turns[-2].text, turns[-4].text)
        is_circular = s1 >= cfg.circularity_threshold and s2 >= cfg.circularity_threshold
        return CircularityRead(
            evaluated=True,
            is_circular=is_circular,
            threshold=cfg.circularity_threshold,
            pair_scores=[s1, s2],
        )
