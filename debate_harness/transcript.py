"""The single shared debate thread and how it is rendered for each debater.

There is one canonical list of turns. When it is a given debater's turn, we
render that shared thread from *their* point of view: their own past turns become
``assistant`` messages, the other debater's become ``user`` messages labelled as
coming from the other side, and the refined question always leads. The
orchestrator's per-turn instruction (which stage is active, what to respond to)
is appended as a final ``user`` message — this is the "dynamic per-turn
injection" layer from spec §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Turn:
    index: int  # 0 = seed, then 1, 2, 3, ...
    speaker_slot: str  # "A" | "B"
    speaker_role: str  # "proposer" | "skeptic"
    stage: int
    text: str
    kind: str = "debate"  # "seed" | "debate" | "elaboration"
    # If this turn replaced an earlier one (elaboration), keep the original.
    superseded_text: Optional[str] = None


@dataclass
class Transcript:
    refined_prompt: str
    turns: list[Turn] = field(default_factory=list)

    def add(self, turn: Turn) -> None:
        self.turns.append(turn)

    @property
    def last(self) -> Optional[Turn]:
        return self.turns[-1] if self.turns else None

    def render_for(
        self,
        slot: str,
        role: str,
        stage: int,
        stage_name: str,
        instruction: str,
    ) -> list[dict[str, str]]:
        """Build the message list to send to the debater in ``slot``."""
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": f"[The question under debate]\n{self.refined_prompt}",
            }
        ]
        for turn in self.turns:
            if turn.speaker_slot == slot:
                messages.append({"role": "assistant", "content": turn.text})
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": f"[The other debater — {turn.speaker_role}]:\n{turn.text}",
                    }
                )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"[Orchestrator] You are the {role}. The debate is in "
                    f"Stage {stage} ({stage_name}). Adopt your Stage {stage} "
                    f"posture as defined in your role instructions.\n\n{instruction}"
                ),
            }
        )
        return messages

    def render_plain(self) -> str:
        """A human-readable rendering of the whole thread (for the judge/logs)."""
        parts = [f"QUESTION: {self.refined_prompt}\n"]
        for turn in self.turns:
            tag = "SEED" if turn.kind == "seed" else f"TURN {turn.index}"
            parts.append(
                f"--- {tag} | {turn.speaker_role.upper()} (slot {turn.speaker_slot}) "
                f"| stage {turn.stage} ---\n{turn.text}\n"
            )
        return "\n".join(parts)
