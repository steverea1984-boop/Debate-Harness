"""Configuration for the debate harness.

Everything tunable lives here. The spec treats almost every number below as a
hypothesis to be corrected by reading real transcripts (§13), so they are knobs,
not constants buried in the loop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# Load .env if present (no-op if python-dotenv isn't installed).
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = ROOT / "roles"
ORCHESTRATOR_DIR = ROOT / "orchestrator"
LOGS_DIR = ROOT / "logs"


@dataclass
class SlotConfig:
    """One of the two debater slots."""

    provider: str  # "anthropic" | "openai" | "openrouter"
    model: str
    role: str  # "proposer" | "skeptic"


@dataclass
class Config:
    # --- Debater slots -----------------------------------------------------
    # Default per spec §9: different models, complementary roles.
    # Slot A -> proposer (Anthropic), Slot B -> skeptic (OpenAI).
    # Each endpoint's provider+model can be overridden by env (SLOT_A_PROVIDER /
    # SLOT_A_MODEL, etc.); the legacy ANTHROPIC_MODEL / OPENAI_MODEL stay as the
    # model fallback so existing setups are unchanged. CLI flags override env.
    slot_a: SlotConfig = field(
        default_factory=lambda: SlotConfig(
            provider=os.environ.get("SLOT_A_PROVIDER", "anthropic"),
            model=os.environ.get(
                "SLOT_A_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
            ),
            role="proposer",
        )
    )
    slot_b: SlotConfig = field(
        default_factory=lambda: SlotConfig(
            provider=os.environ.get("SLOT_B_PROVIDER", "openai"),
            model=os.environ.get(
                "SLOT_B_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o")
            ),
            role="skeptic",
        )
    )

    # --- Orchestrator / observe-only judge ---------------------------------
    orchestrator_provider: str = field(
        default_factory=lambda: os.environ.get("ORCHESTRATOR_PROVIDER", "anthropic")
    )
    orchestrator_model: str = field(
        default_factory=lambda: os.environ.get("ORCHESTRATOR_MODEL", "claude-opus-4-8")
    )
    # The judge is independently selectable; when unset it mirrors the
    # orchestrator (today's behavior). Resolve via the effective_* properties so
    # the fallback always reflects the *final* orchestrator value (e.g. after CLI
    # overrides), regardless of assignment order.
    judge_provider: Optional[str] = field(
        default_factory=lambda: os.environ.get("JUDGE_PROVIDER")
    )
    judge_model: Optional[str] = field(
        default_factory=lambda: os.environ.get("JUDGE_MODEL")
    )

    # --- Interaction mode --------------------------------------------------
    # "debate"  : adversarial proposer vs skeptic; final answer synthesized by the
    #             present step (the original behavior).
    # "build"   : cumulative shared-answer — both slots use the builder role and
    #             revise one growing working answer each turn; the final answer is
    #             that working answer verbatim (no re-synthesis). See
    #             docs/build-mode/spec.md.
    mode: str = "debate"

    # --- Stage schedule (turn-based timer; spec §12) -----------------------
    # Number of *debate* turns spent in each stage (the seed answer is turn 0
    # and is implicitly stage 1). The turn cap is the sum of these. Adjusting
    # these is how you change the cooling rate (open question §Open-2).
    stage1_turns: int = 3
    stage2_turns: int = 3
    stage3_turns: int = 2

    # --- Generation -------------------------------------------------------
    debater_max_tokens: int = 16000
    orchestrator_max_tokens: int = 4000

    # --- Interventions / elaboration (spec §8) -----------------------------
    # Off by default for clean first transcripts. The mechanism exists; turn it
    # on to study whether elaboration improves answers or just bends them (§13).
    max_elaborations: int = 0
    elaboration_cooldown: int = 3  # min turns between elaboration requests

    # --- Judge -------------------------------------------------------------
    # Observe-only by default (spec §13): the judge logs what stage/consensus it
    # *thinks* without driving postures or stopping the debate. Flip this to let
    # the judge's consensus/circularity reads actually end the debate early.
    enable_judge_stop: bool = False

    # --- State-based stage 2->3 transition (spec §7) -----------------------
    # Off by default: the default keeps the pure turn-based timer, judge
    # observe-only. When on, the judge's read drives the 2->3 boundary (1->2
    # stays turn-based), with the safeguards below. The knobs only take effect
    # when the gate is on, and are starting points to tune against transcripts.
    state_based_2to3: bool = False
    min_stage2_turns: int = 1  # min stage-2 turns before state can advance to 3
    stage_transition_confidence: float = 0.6  # min judge confidence to act on a read
    max_stage_reversals: int = 1  # cap on 3->2 reversions (anti-thrash)

    # --- Circularity detection (spec §10) ----------------------------------
    # Off by default: the structural detector still runs and logs every turn
    # (observe-only), but only the turn cap stops the debate. When the gate is
    # on, a circular read ends the debate early (stop_reason "circular"). Knobs
    # only take effect for the verdict; the read is logged either way.
    enable_circularity_stop: bool = False
    circularity_threshold: float = 0.6  # min same-speaker similarity to count as restatement
    circularity_min_turns: int = 4  # min debate turns before the detector can fire

    # --- Clarification -----------------------------------------------------
    # Interactive runs may ask the user clarifying questions before refining.
    # Batch runs never can, so they skip straight to refinement.
    clarify: bool = True

    @property
    def turn_cap(self) -> int:
        return self.stage1_turns + self.stage2_turns + self.stage3_turns

    @property
    def effective_judge_provider(self) -> str:
        """Judge provider, falling back to the orchestrator's when unset."""
        return self.judge_provider or self.orchestrator_provider

    @property
    def effective_judge_model(self) -> str:
        """Judge model, falling back to the orchestrator's when unset."""
        return self.judge_model or self.orchestrator_model

    def stage_for_turn(self, debate_turn: int) -> int:
        """Map a 1-based debate turn index to its scheduled stage.

        Turn 0 is the seed (stage 1). Turns 1..n1 are stage 1, the next n2 are
        stage 2, the remainder stage 3.
        """
        if debate_turn <= 0:
            return 1
        if debate_turn <= self.stage1_turns:
            return 1
        if debate_turn <= self.stage1_turns + self.stage2_turns:
            return 2
        return 3

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["turn_cap"] = self.turn_cap
        # Record the *resolved* judge endpoint (not the None placeholder) so each
        # run.json shows which model actually played the judge.
        d["judge_provider"] = self.effective_judge_provider
        d["judge_model"] = self.effective_judge_model
        return d


STAGE_NAMES = {
    1: "Surface & stress",
    2: "Work the disagreements",
    3: "Resolve",
}

# Build mode reuses the 3-stage schedule but with build-appropriate posture names.
BUILD_STAGE_NAMES = {
    1: "Draft & expand",
    2: "Challenge & refine",
    3: "Finalize",
}
