"""The orchestrator: referee, prompt-engineer, and turn-shuttle.

It never debates. It refines the prompt, seeds the debate by picking the stronger
of two independent opening answers, names the active stage each turn, shuttles
turns between the two debaters, runs the observe-only judge after every turn, and
presents the final result. Stage transitions follow a simple turn-based timer
(spec §12); the judge only watches unless ``enable_judge_stop`` is set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import Config, ORCHESTRATOR_DIR, ROLES_DIR, STAGE_NAMES
from .judge import Judge, JudgeRead, TERMINAL_SHAPES
from .logging_utils import RunLogger
from .circularity import CircularityDetector
from .providers import Provider, make_provider
from .stages import StageController
from .transcript import Transcript, Turn


# ----------------------------------------------------------------------------
# Role-file loading (spec §5: baseline + role overlay = the debater's system prompt)
# ----------------------------------------------------------------------------
def _read(path) -> str:
    return path.read_text(encoding="utf-8").strip()


def build_debater_system(role: str) -> str:
    baseline = _read(ROLES_DIR / "baseline.md")
    overlay = _read(ROLES_DIR / f"{role}.md")
    return f"{baseline}\n\n---\n\n{overlay}"


# ----------------------------------------------------------------------------
# Debater agent: a provider + its standing role system prompt
# ----------------------------------------------------------------------------
class Debater:
    def __init__(self, slot: str, provider: Provider, role: str, max_tokens: int):
        self.slot = slot
        self.provider = provider
        self.role = role
        self.system = build_debater_system(role)
        self.max_tokens = max_tokens

    def seed_answer(self, refined_prompt: str) -> str:
        instruction = (
            f"[Orchestrator] You are the {self.role}. The debate is in Stage 1 "
            f"({STAGE_NAMES[1]}). Give your initial answer to the question, "
            "adopting your Stage 1 posture. This is your opening position."
        )
        messages = [
            {"role": "user", "content": f"[The question under debate]\n{refined_prompt}"},
            {"role": "user", "content": instruction},
        ]
        return self.provider.complete(self.system, messages, self.max_tokens)

    def respond(
        self, transcript: Transcript, stage: int, instruction: str
    ) -> str:
        messages = transcript.render_for(
            self.slot, self.role, stage, STAGE_NAMES[stage], instruction
        )
        return self.provider.complete(self.system, messages, self.max_tokens)


# ----------------------------------------------------------------------------
# Orchestrator JSON schemas
# ----------------------------------------------------------------------------
_REFINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "needs_clarification": {"type": "boolean"},
        "clarifying_questions": {"type": "array", "items": {"type": "string"}},
        "refined_prompt": {"type": "string"},
    },
    "required": ["needs_clarification", "clarifying_questions", "refined_prompt"],
}

_SEED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "seed_slot": {"type": "string", "enum": ["A", "B"]},
        "criteria": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["seed_slot", "criteria", "reasoning"],
}

_PRESENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "outcome_type": {
            "type": "string",
            "enum": [
                "genuine_consensus",
                "productive_stalemate",
                "circular_no_convergence",
                "turn_cap_no_convergence",
            ],
        },
        "final_answer": {"type": "string"},
        "residual_disagreement": {"type": "string"},
        "note_to_user": {"type": "string"},
    },
    "required": [
        "outcome_type",
        "final_answer",
        "residual_disagreement",
        "note_to_user",
    ],
}

_ELABORATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "request_elaboration": {"type": "boolean"},
        "instruction": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["request_elaboration", "instruction", "reason"],
}


@dataclass
class DebateResult:
    transcript: Transcript
    outcome_type: str
    final_answer: str
    residual_disagreement: str
    note_to_user: str
    stop_reason: str
    log_dir: str


class Orchestrator:
    def __init__(self, config: Config, logger: Optional[RunLogger] = None):
        self.config = config
        self.system = _read(ORCHESTRATOR_DIR / "system.md")
        self.orch = make_provider(config.orchestrator_provider, config.orchestrator_model)
        # The judge has its own provider instance; by default it mirrors the
        # orchestrator's provider+model, but it can be pointed at a cheaper model
        # independently (the judge runs after every turn — the biggest cost lever).
        self.judge = Judge(
            make_provider(config.effective_judge_provider, config.effective_judge_model),
            config.orchestrator_max_tokens,
        )
        self.debaters = {
            "A": Debater(
                "A",
                make_provider(config.slot_a.provider, config.slot_a.model),
                config.slot_a.role,
                config.debater_max_tokens,
            ),
            "B": Debater(
                "B",
                make_provider(config.slot_b.provider, config.slot_b.model),
                config.slot_b.role,
                config.debater_max_tokens,
            ),
        }
        self.log = logger or RunLogger()

    # --- 1. Refine the prompt --------------------------------------------
    def refine_prompt(
        self, raw_prompt: str, ask_user: Optional[Callable[[list[str]], dict[str, str]]] = None
    ) -> str:
        user = (
            "Refine the following raw user prompt into a tight, debate-ready "
            "prompt. If it is too vague to do that well, list targeted clarifying "
            "questions. Do not answer the question yourself.\n\n"
            f"RAW PROMPT:\n{raw_prompt}"
        )
        data = self.orch.complete_json(
            self.system, user, _REFINE_SCHEMA, self.config.orchestrator_max_tokens
        )
        # Fall back to the raw prompt if the orchestrator returns an empty (or
        # missing) refined prompt — a weak orchestrator model can do this, and an
        # empty question unmoors the whole debate into hallucination.
        refined = (data.get("refined_prompt") or "").strip() or raw_prompt
        questions = data.get("clarifying_questions", []) or []

        if (
            self.config.clarify
            and data.get("needs_clarification")
            and questions
            and ask_user is not None
        ):
            answers = ask_user(questions)
            qa = "\n".join(f"Q: {q}\nA: {answers.get(q, '(no answer)')}" for q in questions)
            user2 = (
                "Incorporate the user's clarifications and produce the final "
                "refined, debate-ready prompt.\n\n"
                f"RAW PROMPT:\n{raw_prompt}\n\nCLARIFICATIONS:\n{qa}"
            )
            data2 = self.orch.complete_json(
                self.system, user2, _REFINE_SCHEMA, self.config.orchestrator_max_tokens
            )
            refined = (data2.get("refined_prompt") or "").strip() or refined
            self.log.event(
                "clarify", questions=questions, answers=answers, refined=refined
            )

        self.log.event("refine", raw=raw_prompt, refined=refined, questions=questions)
        self.log.md_header("Refined prompt")
        self.log.md(refined)
        return refined

    # --- 2. Seed the debate ----------------------------------------------
    def seed(self, refined_prompt: str) -> Transcript:
        ans_a = self.debaters["A"].seed_answer(refined_prompt)
        ans_b = self.debaters["B"].seed_answer(refined_prompt)
        self.log.event("seed_answer", slot="A", role=self.debaters["A"].role, text=ans_a)
        self.log.event("seed_answer", slot="B", role=self.debaters["B"].role, text=ans_b)

        user = (
            "Both debaters answered the refined prompt independently. Pick the "
            "stronger answer to SEED the sequential debate (the other model will "
            "respond to it). Judge by comprehensiveness, clarity, and relevance — "
            "and note that the best seed for sparking a good debate is not always "
            "the safest answer. Judge form, not which side is 'right'.\n\n"
            f"REFINED PROMPT:\n{refined_prompt}\n\n"
            f"ANSWER A ({self.debaters['A'].role}):\n{ans_a}\n\n"
            f"ANSWER B ({self.debaters['B'].role}):\n{ans_b}"
        )
        data = self.orch.complete_json(
            self.system, user, _SEED_SCHEMA, self.config.orchestrator_max_tokens
        )
        seed_slot = data.get("seed_slot", "A")
        seed_text = ans_a if seed_slot == "A" else ans_b
        seed_role = self.debaters[seed_slot].role

        transcript = Transcript(refined_prompt=refined_prompt)
        transcript.add(
            Turn(
                index=0,
                speaker_slot=seed_slot,
                speaker_role=seed_role,
                stage=1,
                text=seed_text,
                kind="seed",
            )
        )
        self.log.event(
            "seed_selection",
            seed_slot=seed_slot,
            seed_role=seed_role,
            criteria=data.get("criteria"),
            reasoning=data.get("reasoning"),
        )
        self.log.md_header("Seed selection")
        self.log.md(f"Seeded with slot **{seed_slot}** ({seed_role}).\n")
        self.log.md(f"*Criteria:* {data.get('criteria','')}\n")
        self.log.md(f"*Reasoning:* {data.get('reasoning','')}\n")
        self.log.md_header(f"Seed answer — {seed_role} (slot {seed_slot})", level=3)
        self.log.md(seed_text)
        return transcript

    # --- optional elaboration (spec §8; off unless max_elaborations > 0) ---
    def _maybe_elaborate(
        self, transcript: Transcript, stage: int, turns_since_elab: int, used: int
    ) -> tuple[bool, int]:
        cfg = self.config
        if used >= cfg.max_elaborations or turns_since_elab < cfg.elaboration_cooldown:
            return False, used
        last = transcript.last
        user = (
            "You may optionally ask the debater who just spoke to strengthen ONE "
            "thin or unsupported part of their own response before the handoff. "
            "Do this only on a clear quality problem — comment on form, never "
            "content, and never hand them an argument. If the response is fine, "
            "do not request elaboration.\n\n"
            f"MOST RECENT TURN ({last.speaker_role}):\n{last.text}"
        )
        data = self.orch.complete_json(
            self.system, user, _ELABORATION_SCHEMA, self.config.orchestrator_max_tokens
        )
        if not data.get("request_elaboration"):
            return False, used

        instruction = data.get("instruction", "")
        debater = self.debaters[last.speaker_slot]
        revised = debater.respond(
            transcript,
            stage,
            f"[Orchestrator — elaboration] {instruction} "
            "Revise and strengthen your most recent response accordingly; "
            "produce the improved version of that turn.",
        )
        last.superseded_text = last.text
        last.text = revised
        last.kind = "elaboration"
        self.log.event(
            "elaboration",
            slot=last.speaker_slot,
            instruction=instruction,
            reason=data.get("reason"),
            revised_text=revised,
        )
        self.log.md_header(f"Elaboration request → slot {last.speaker_slot}", level=3)
        self.log.md(f"*Instruction:* {instruction}\n")
        self.log.md(f"**Revised turn:**\n{revised}")
        return True, used + 1

    # --- 3. Run the debate loop ------------------------------------------
    def run_debate(self, transcript: Transcript) -> tuple[str, JudgeRead]:
        cfg = self.config
        seed = transcript.turns[0]
        # The non-seeding model responds first, then turns alternate.
        current = "B" if seed.speaker_slot == "A" else "A"

        stop_reason = "turn_cap"
        last_read: Optional[JudgeRead] = None
        elaborations_used = 0
        turns_since_elab = cfg.elaboration_cooldown  # allow from the start
        controller = StageController(cfg)
        detector = CircularityDetector(cfg)

        for debate_turn in range(1, cfg.turn_cap + 1):
            stage = controller.current_stage(debate_turn)
            debater = self.debaters[current]
            instruction = (
                "Respond to the other debater's most recent turn in the shared "
                "thread above. Engage their strongest point directly."
            )
            text = debater.respond(transcript, stage, instruction)
            turn = Turn(
                index=debate_turn,
                speaker_slot=current,
                speaker_role=debater.role,
                stage=stage,
                text=text,
                kind="debate",
            )
            transcript.add(turn)
            self.log.event(
                "turn",
                index=debate_turn,
                slot=current,
                role=debater.role,
                stage=stage,
                stage_name=STAGE_NAMES[stage],
                text=text,
            )
            self.log.md_header(
                f"Turn {debate_turn} — {debater.role} (slot {current}) "
                f"| Stage {stage} ({STAGE_NAMES[stage]})",
                level=3,
            )
            self.log.md(text)

            # Optional elaboration on the turn just produced.
            did_elab, elaborations_used = self._maybe_elaborate(
                transcript, stage, turns_since_elab, elaborations_used
            )
            turns_since_elab = 0 if did_elab else turns_since_elab + 1

            # Observe-only judge after every turn.
            read = self.judge.read(transcript, stage)
            last_read = read
            self.log.event(
                "judge_read",
                after_turn=debate_turn,
                scheduled_stage=stage,
                perceived_stage=read.perceived_stage,
                consensus_shape=read.consensus_shape,
                confidence=read.confidence,
                should_stop=read.should_stop,
                reason=read.reason,
            )
            self.log.md(
                f"> **Judge (observe-only):** perceived stage = "
                f"`{read.perceived_stage}` | consensus = `{read.consensus_shape}` "
                f"| confidence = {read.confidence:.2f}\n>\n> {read.reason}\n"
            )

            # Stage management. In the default (timer) mode this never transitions
            # off-schedule; in state mode the judge's read can drive the 2->3
            # boundary (and step back). Either way, log every stage decision.
            controller.observe(debate_turn, read)
            if controller.last_transition:
                t = controller.last_transition
                self.log.event(
                    "stage_transition",
                    after_turn=debate_turn,
                    from_stage=t["from"],
                    to_stage=t["to"],
                    reason=t["reason"],
                )
                self.log.md(
                    f"> **Stage transition:** {t['from']} → {t['to']} "
                    f"(`{t['reason']}`)\n"
                )

            # Structural circularity check (observe-only; logged every turn).
            cread = detector.read(transcript)
            self.log.event(
                "circularity_read",
                after_turn=debate_turn,
                evaluated=cread.evaluated,
                scores=cread.pair_scores,
                is_circular=cread.is_circular,
            )
            if cread.evaluated:
                self.log.md(
                    "> **Circularity (observe-only):** scores="
                    f"{[round(s, 2) for s in cread.pair_scores]} "
                    f"| circular = {cread.is_circular}\n"
                )

            # The judge only stops the debate if explicitly enabled (§13).
            if (
                cfg.enable_judge_stop
                and read.should_stop
                and read.consensus_shape in TERMINAL_SHAPES
            ):
                stop_reason = f"judge:{read.consensus_shape}"
                break

            # Circularity is a separate, opt-in backstop (spec §10).
            if cfg.enable_circularity_stop and cread.is_circular:
                stop_reason = "circular"
                break

            current = "B" if current == "A" else "A"

        self.log.event("stop", reason=stop_reason)
        return stop_reason, last_read

    # --- 4. Present the result -------------------------------------------
    def present(
        self, transcript: Transcript, stop_reason: str, last_read: Optional[JudgeRead]
    ) -> DebateResult:
        judge_note = ""
        if last_read is not None:
            judge_note = (
                f"The observe-only judge's final read was consensus="
                f"{last_read.consensus_shape}, perceived_stage="
                f"{last_read.perceived_stage} (confidence {last_read.confidence:.2f}). "
                "Treat this as one more signal, not ground truth."
            )
        user = (
            "The debate has stopped (reason: "
            f"{stop_reason}). Present the final result to the user. If the models "
            "reached genuine consensus, present the agreed answer. If they reached "
            "a productive stalemate, present the answer WITH the irreducible "
            "tradeoff stated cleanly and each side's reasoning. If they did not "
            "converge (circularity or turn cap), present the best available "
            "synthesis and clearly flag the non-convergence. Do not take a side or "
            "inject your own position.\n\n"
            f"{judge_note}\n\nFULL DEBATE:\n{transcript.render_plain()}"
        )
        data = self.orch.complete_json(
            self.system, user, _PRESENT_SCHEMA, self.config.orchestrator_max_tokens
        )
        result = DebateResult(
            transcript=transcript,
            outcome_type=data.get("outcome_type", "turn_cap_no_convergence"),
            final_answer=data.get("final_answer", ""),
            residual_disagreement=data.get("residual_disagreement", ""),
            note_to_user=data.get("note_to_user", ""),
            stop_reason=stop_reason,
            log_dir=str(self.log.dir),
        )
        self.log.event(
            "present",
            outcome_type=result.outcome_type,
            final_answer=result.final_answer,
            residual_disagreement=result.residual_disagreement,
            note_to_user=result.note_to_user,
        )
        self.log.md_header("Final result")
        self.log.md(f"**Outcome:** {result.outcome_type}\n")
        self.log.md(f"**Answer:**\n{result.final_answer}\n")
        if result.residual_disagreement.strip():
            self.log.md(f"**Residual disagreement:**\n{result.residual_disagreement}\n")
        if result.note_to_user.strip():
            self.log.md(f"**Note:** {result.note_to_user}\n")
        return result

    # --- end-to-end -------------------------------------------------------
    def run(
        self,
        raw_prompt: str,
        ask_user: Optional[Callable[[list[str]], dict[str, str]]] = None,
    ) -> DebateResult:
        self.log.set("config", self.config.to_dict())
        self.log.set("raw_prompt", raw_prompt)
        self.log.set(
            "slots",
            {
                "A": {"provider": self.config.slot_a.provider, "model": self.config.slot_a.model, "role": self.config.slot_a.role},
                "B": {"provider": self.config.slot_b.provider, "model": self.config.slot_b.model, "role": self.config.slot_b.role},
            },
        )
        self.log.md_header(f"Debate run — {self.log.dir.name}", level=1)
        self.log.md(f"**Raw prompt:** {raw_prompt}\n")

        refined = self.refine_prompt(raw_prompt, ask_user=ask_user)
        transcript = self.seed(refined)
        stop_reason, last_read = self.run_debate(transcript)
        result = self.present(transcript, stop_reason, last_read)
        self.log.finalize(
            outcome_type=result.outcome_type,
            stop_reason=stop_reason,
            turns=len(transcript.turns),
        )
        return result
