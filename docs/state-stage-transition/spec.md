# Spec: State-based stage 2→3 transition

## What

Add an **optional** state-driven 2→3 stage transition. Today every turn's stage
is a pure function of the turn index (`config.stage_for_turn`). This feature lets
the observe-only judge's per-turn read *drive* the 2→3 boundary — advancing to
stage 3 ("Resolve") when it reads the surfaced disagreements as mostly resolved,
and stepping back to stage 2 if a later read shows the models are still far apart
— while the 1→2 boundary stays turn-based and the hard turn cap remains the
backstop. It is **off by default** (the default stays the pure timer, judge
observe-only); turning it on is the first deliberate step toward the judge
driving postures, built with the spec's degrade-gracefully safeguards (gradual,
reversible, turn-capped) per §7/§13.

## Context

- `debate_harness/orchestrator.py` → `Orchestrator.run_debate` computes
  `stage = cfg.stage_for_turn(debate_turn)` each turn, generates the debater turn
  at that stage, then calls `self.judge.read(transcript, stage)` (observe-only).
  The read (`JudgeRead`: `perceived_stage` ∈ surface/working/resolving,
  `consensus_shape`, `confidence`, `should_stop`, `reason`) is logged but only
  acts when `cfg.enable_judge_stop` is set.
- `debate_harness/config.py` → `stage_for_turn` maps a 1-based debate turn to a
  stage from cumulative `stage1_turns`/`stage2_turns`/`stage3_turns`;
  `turn_cap` = their sum.
- Design spec §7: "**1→2** is hard to judge on state → lean **turn-based** with a
  minimum number of stage-1 turns. **2→3** is state-detectable → lean
  **state-based**, with the turn cap as backstop." Transitions must be **gradual**
  (one stage at a time, no skipping) and **reversible** (step back if still far
  apart). §13: the judge "degrades gracefully" precisely because it's gradual +
  reversible + turn-capped — this feature is where that safety story first
  matters.
- Offline test pattern already exists: `tests/test_offline_loop.py` drives the
  loop with a stub provider and a stub judge (no API keys, runs in CI).

## Requirements

1. A config gate `state_based_2to3` (default `False`). When `False`, behavior is
   **byte-identical** to today: stage = `stage_for_turn(debate_turn)`.
2. When `True`, the **1→2** transition stays turn-based (advance after
   `stage1_turns` turns), and the **2→3** transition is state-driven:
   - advance 2→3 when the judge read indicates resolution **and** at least
     `min_stage2_turns` turns have been spent in stage 2;
   - as a backstop, advance 2→3 by the timer once `stage2_turns` stage-2 turns
     have elapsed even without a resolving read;
   - never skip a stage (no 1→3).
3. **Reversible:** while in stage 3, step back to stage 2 if a later read clearly
   shows the models are still far apart — bounded by `max_stage_reversals` to
   prevent thrash.
4. The **hard turn cap is unchanged** — the debate still runs at most `turn_cap`
   debate turns regardless of stage.
5. Every stage change is **logged** as a distinct event with its reason
   (`timer` / `state_advance` / `state_revert`), satisfying §12's "every stage
   decision" logging.
6. The whole mechanism is **offline-unit-testable** with synthetic judge reads
   (no LLM, no network), and the existing offline loop test still passes.
7. Optional CLI flag to enable it for live runs.

## Design

### New component: `debate_harness/stages.py` → `StageController`

A small, LLM-free state machine that owns the "what stage is this turn" decision.
It takes the `Config` and consumes **duck-typed** judge reads (any object with
`.perceived_stage`, `.consensus_shape`, `.confidence`) — it does **not** import
`judge` (avoids an import cycle; `judge.JudgeRead` satisfies the shape).

```
class StageController:
    def __init__(self, config): ...        # mode = config.state_based_2to3
    def current_stage(self, debate_turn: int) -> int
    def observe(self, debate_turn: int, read) -> None   # call after each turn's read
    last_transition: Optional[dict]        # {from, to, reason} or None, for logging
```

- **Timer mode** (`state_based_2to3 is False`): `current_stage(t)` returns
  `config.stage_for_turn(t)`; `observe()` is a no-op. This reproduces today's
  behavior exactly (guarded by a test, see below).
- **State mode** (`True`): the controller maintains `self.stage` (starts at 1) and
  `self.turns_in_stage`. `current_stage()` returns `self.stage`; `observe()`
  updates it for the next turn using the read just produced:
  - **stage 1:** when `turns_in_stage1 >= config.stage1_turns` → stage 2 (reason
    `timer`).
  - **stage 2:** let
    - `resolved = read is not None and read.confidence >= config.stage_transition_confidence and (read.perceived_stage == "resolving" or read.consensus_shape in {"genuine_consensus", "productive_stalemate"})`
    - if `turns_in_stage2 >= config.min_stage2_turns and resolved` → stage 3
      (reason `state_advance`);
    - elif `turns_in_stage2 >= config.stage2_turns` → stage 3 (reason `timer`,
      backstop);
  - **stage 3:** let
    - `far_apart = read is not None and read.confidence >= config.stage_transition_confidence and read.perceived_stage == "surface"`
    - if `far_apart and reversals < config.max_stage_reversals` → stage 2
      (reason `state_revert`, `reversals += 1`).

  On any change, reset `turns_in_stage` and set `last_transition`.

### `run_debate` integration (`orchestrator.py`)

Replace the inline `stage = cfg.stage_for_turn(debate_turn)` with a controller:

```
controller = StageController(cfg)
for debate_turn in 1..turn_cap:
    stage = controller.current_stage(debate_turn)
    ... generate turn, log turn (unchanged) ...
    ... elaboration (unchanged) ...
    read = self.judge.read(transcript, stage)   # unchanged
    ... log judge_read (unchanged) ...
    controller.observe(debate_turn, read)
    if controller.last_transition:               # log + md note
        self.log.event("stage_transition", after_turn=debate_turn, **controller.last_transition)
    ... existing judge-stop check (unchanged) ...
    current = swap speaker
```

Single code path; mode lives in the controller. The judge call and the
`enable_judge_stop` logic are untouched — this feature is orthogonal to stopping.

### Config additions (`config.py`)

```
state_based_2to3: bool = False        # gate; default keeps pure timer
min_stage2_turns: int = 1             # min stage-2 turns before state can advance
stage_transition_confidence: float = 0.6  # min judge confidence to act on a read
max_stage_reversals: int = 1          # cap 3->2 reversions (anti-thrash)
```

`to_dict()` already serializes all fields via `asdict`, so these are logged with
the run config automatically.

### CLI (`cli.py`)

Add `--state-2to3` (sets `state_based_2to3 = True`). Keep the four numeric knobs
config-only for now (env/Config), to avoid flag sprawl.

## Decisions

- **Off by default, single gate.** *Chosen:* `state_based_2to3=False` preserves
  today's behavior exactly. *Why:* §13 wants observe-only first; we're not
  changing the default until transcripts justify it. *Reversible:* yes.
- **Controller object vs. inline branching.** *Chosen:* a `StageController` in its
  own module. *Alternative:* an `if cfg.state_based_2to3` branch inside
  `run_debate`. *Why the controller:* the transition logic is stateful and the
  part most worth testing in isolation without an LLM; a class makes it unit-
  testable with synthetic reads. *Reversible:* yes.
- **Resolution predicate.** *Chosen:* `perceived_stage == "resolving"` OR a
  terminal consensus shape (`genuine_consensus`/`productive_stalemate`), gated by
  a confidence floor. *Alternative:* require `should_stop`. *Why not:*
  `should_stop` is about ending the debate, not about the postures cooling; a
  debate can be ready to *work toward* resolution before it's ready to *stop*.
  *Reversible:* yes (it's a single function).
- **Reversal only on `perceived_stage == "surface"`.** *Chosen:* conservative —
  only revert when the judge says they're clearly back to surfacing, which is the
  §7 "premature cool-down should self-correct" case. *Alternative:* also revert on
  high-confidence `disagreement`. *Why not (default):* `working` + disagreement is
  the *normal* stage-2 state and would cause thrash. *Reversible:* yes; capped by
  `max_stage_reversals`.
- **Timer backstop for 2→3 reuses `stage2_turns`.** *Chosen:* once `stage2_turns`
  turns have elapsed in stage 2, force-advance even without a resolving read, so
  stage 3 still happens if the judge never signals. *Reversible:* yes.
- `Assumption:` the existing `JudgeRead` fields (`perceived_stage`,
  `consensus_shape`, `confidence`) are the right signals; if they change, the
  controller's duck-typed predicates move with them.
- `Assumption:` default knob values (`min_stage2_turns=1`, confidence `0.6`,
  `max_stage_reversals=1`) are starting points to be tuned against real
  transcripts, consistent with the spec's "treat as experiment" stance — they
  only take effect when the gate is on.

## Invariants

- **Default behavior unchanged:** with `state_based_2to3=False`, the per-turn
  stage sequence equals `[stage_for_turn(t) for t in 1..turn_cap]`. *Check:* a
  unit test asserts timer-mode `StageController` matches `stage_for_turn` across
  several schedules; the existing `tests/test_offline_loop.py` still passes
  unchanged.
- **No stage skipping:** transitions only ever move ±1 stage. *Check:* a unit
  test feeding adversarial reads asserts the stage never jumps 1→3 or 3→1.
- **Turn cap holds:** the loop runs ≤ `turn_cap` debate turns in every mode.
  *Check:* offline loop test asserts turn count.
- **No infinite reversal thrash:** reversals are bounded by `max_stage_reversals`.
  *Check:* unit test with repeated "surface" reads asserts at most N reversions.

## Error Behavior

- A `None` read (shouldn't happen mid-loop, but defensive) → no state transition
  that turn; the controller holds its current stage.
- Unknown `perceived_stage`/`consensus_shape` strings → treated as "not a
  resolution / not far-apart" signal (no transition), never an exception.

## Testing Strategy

- **New `tests/test_stage_controller.py`** (stdlib `unittest`, offline):
  - timer-mode controller == `stage_for_turn` for ≥2 schedules;
  - state mode: holds stage 2 until `min_stage2_turns`; advances on a
    high-confidence resolving read; backstops to 3 by `stage2_turns` without one;
    reverts 3→2 on a high-confidence `surface` read; respects
    `max_stage_reversals`; never skips a stage; ignores low-confidence reads.
- **Extend `tests/test_offline_loop.py`**: add a case with
  `state_based_2to3=True` and a stub judge returning a resolving read, asserting
  the loop reaches stage 3 earlier than the timer would and still stops at the
  turn cap. The existing default-mode test stays as the unchanged-behavior guard.
- CI (`.github/workflows/ci.yml`) runs all of the above with no keys → stays
  green.

## Out of Scope

- Making the 1→2 transition state-based (stays turn-based per §7).
- Changing `enable_judge_stop` / stopping logic (orthogonal).
- Judgment-quality evaluation of the judge (the separate §13 eval feature).
- Per-stage role changes, desynchronized schedules, parallel execution.
- Turning the feature on by default (a later decision, once transcripts justify
  it).
