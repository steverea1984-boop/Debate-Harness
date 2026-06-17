"""Observe-only consensus / stage judge (spec §10, §13).

This is the testing-discipline centerpiece: an LLM that *watches* the debate and
logs, after every turn, (a) what stage it thinks the debate is really in and
(b) whether the models have reached genuine consensus, a productive stalemate,
circularity, or none of the above — **without** driving the postures or stopping
the debate. The whole point (§13) is to find out whether this judgment can be
trusted by comparing its reads against the transcript before we ever let it
steer.

If ``Config.enable_judge_stop`` is set, the orchestrator may act on a confident
read; by default it does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .providers import Provider
from .transcript import Transcript


JUDGE_SYSTEM = """You are an observer of a structured debate between two AI models \
(a proposer and a skeptic). You are NOT a participant and you have NO opinion on \
the question itself. Your only job is to read the exchange and report on its shape.

You judge form, never content. You never say which side is right.

You assess two things:
1. STAGE: which phase the debate is actually in, judged from the exchange itself,
   independent of whatever stage the orchestrator has scheduled:
     - "surface"  : still surfacing weaknesses; new objections still appearing.
     - "working"  : the surfaced disagreements are being pursued to resolution;
                    few or no new objections.
     - "resolving": converging with stated reasons, or naming an irreducible
                    tradeoff cleanly.
2. CONSENSUS shape:
     - "disagreement"        : substantive open disagreement remains.
     - "genuine_consensus"   : earned agreement, reached gradually, with the
                               agreeing side able to say what changed its mind.
     - "capitulation"        : one side folded WITHOUT an articulable reason, or
                               agreement collapsed suddenly in a single turn.
                               This is a RED FLAG, not a stop.
     - "productive_stalemate": a genuine, well-articulated disagreement / an
                               irreducible tradeoff. A valid terminal state.
     - "circular"            : the last two exchanges restate the previous two.

Be skeptical of agreement. Gradual narrowing with stated reasons is trustworthy;
a sudden jump from disagreement to total agreement is suspect. Distinguish
"genuine_consensus" from "capitulation" carefully — that distinction is the most
important thing you do."""


JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "perceived_stage": {
            "type": "string",
            "enum": ["surface", "working", "resolving"],
        },
        "consensus_shape": {
            "type": "string",
            "enum": [
                "disagreement",
                "genuine_consensus",
                "capitulation",
                "productive_stalemate",
                "circular",
            ],
        },
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "should_stop": {"type": "boolean"},
    },
    "required": [
        "perceived_stage",
        "consensus_shape",
        "confidence",
        "reason",
        "should_stop",
    ],
}


@dataclass
class JudgeRead:
    perceived_stage: str
    consensus_shape: str
    confidence: float
    reason: str
    should_stop: bool
    raw: dict[str, Any]


# Consensus shapes that are legitimate terminal states (vs. open disagreement).
TERMINAL_SHAPES = {"genuine_consensus", "productive_stalemate", "circular"}


class Judge:
    def __init__(self, provider: Provider, max_tokens: int):
        self._provider = provider
        self._max_tokens = max_tokens

    def read(self, transcript: Transcript, scheduled_stage: int) -> JudgeRead:
        user = (
            f"The orchestrator currently has the debate scheduled in Stage "
            f"{scheduled_stage}, but judge the exchange on its own terms.\n\n"
            "Here is the debate so far:\n\n"
            f"{transcript.render_plain()}\n\n"
            "Report your read. Set should_stop = true ONLY if the consensus shape "
            "is genuine_consensus, productive_stalemate, or circular AND you are "
            "confident; otherwise false."
        )
        data = self._provider.complete_json(
            JUDGE_SYSTEM, user, JUDGE_SCHEMA, self._max_tokens
        )
        return JudgeRead(
            perceived_stage=str(data.get("perceived_stage", "surface")),
            consensus_shape=str(data.get("consensus_shape", "disagreement")),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "")),
            should_stop=bool(data.get("should_stop", False)),
            raw=data,
        )
