# Spec: build mode — cumulative shared-answer architecture

## What

Add a second debate **mode** to the harness — `build` — alongside the existing
`debate` mode. Instead of an adversarial conversation that gets lossily
re-summarized at the end, build mode treats the answer as a **living, growing
artifact**: the orchestrator carries a single **working answer** that each turn the
active model revises — preserving what it agrees with, adding detail, and contesting
specific points *with reasons* (and pruning ones that are wrong). The **final answer
is the last working answer verbatim**, not a re-synthesis. Default mode stays
`debate`; build mode is opt-in via `--mode build`.

## Context

This session's goal experiment surfaced two ways the current harness loses detail —
and build mode targets both:

1. **The roles discourage carrying the answer.** `roles/baseline.md` tells debaters
   *"Be concise and substantive. Do not pad, **restate**, or perform thoroughness,"*
   and the skeptic is told to *"find the weakest part"* and *"concede nothing yet."*
   So each turn engages the **contested chunks**, not the whole answer; the "story"
   does not stay intact.
2. **The final answer is a lossy re-summary.** The answer only gets assembled at the
   end by `Orchestrator.present()`, which re-summarizes the transcript. Measured: in
   the goal experiment the debate finals were **2–4× shorter** than a single model's
   answer — detail generated mid-debate dies at synthesis.

Relevant code:
- [orchestrator.py](../../debate_harness/orchestrator.py) — `run()` (refine → seed →
  `run_debate` → `present` → finalize), `run_debate` (the per-turn alternation loop,
  lines ~312–434), `present` (~437), `Debater.respond` (~60), `build_debater_system`
  (~31), `seed` (~216).
- [roles/baseline.md](../../roles/baseline.md), [proposer.md](../../roles/proposer.md),
  [skeptic.md](../../roles/skeptic.md) — current adversarial roles.
- [config.py](../../debate_harness/config.py) — the knob hub; [cli.py](../../debate_harness/cli.py)
  (`build_parser`/`_build_config`); [transcript.py](../../debate_harness/transcript.py)
  (shared thread + `render_plain`); [judge.py](../../debate_harness/judge.py)
  (observe-only judge); [logging_utils.py](../../debate_harness/logging_utils.py).
- [tests/test_offline_loop.py](../../tests/test_offline_loop.py) — the stub-provider
  pattern (CI installs **no deps**; tests stay stub-only).

## Requirements

1. `--mode build` (and `Config.mode = "build"`) runs the cumulative shared-answer
   loop; `mode = "debate"` (default) is **byte-for-byte today's behavior**.
2. Build mode carries a single **working answer** across turns. Each turn the active
   model returns a **full revised working answer** plus a short **changelog** (kept /
   added / challenged / removed, each with a reason).
3. The **final answer = the last working answer**, passed through verbatim — *not*
   re-summarized. The present step in build mode only classifies metadata
   (`outcome_type`, `residual_disagreement`, `note_to_user`); it never rewrites the
   answer.
4. Build mode **accumulates and prunes**: agreed/strong detail is preserved and
   extended; a point challenged with a reason that goes unanswered is removed or
   revised. Every change is justified in the changelog. An anti-thrash rule keeps
   remove/restore loops bounded.
5. The working answer + changelog for every turn are logged (run.json events +
   transcript.md) so the artifact's growth is auditable.
6. All existing tests pass; new offline stub tests prove the build loop carries +
   revises the working answer and that `final_answer == last working answer`.

## Design

### Mode switch (`config.py`, `cli.py`)

- `Config.mode: str = "debate"`.
- `cli.py`: `--mode {debate,build}` (default `debate`), wired in `_build_config`.
- `Orchestrator.run()` branches once: `mode == "build"` → `run_build()` + pass-through
  present; else the existing `run_debate()` + `present()`. `refine` and `seed` are
  shared.

### Roles (`roles/`)

Build mode needs a **non-adversarial baseline** (the current baseline's "do not
restate" directly conflicts with carrying the whole answer). Add two files, mirroring
the existing baseline+overlay pattern; **both slots use the same builder role** (a
symmetric collaborator):

- `roles/build_baseline.md` — shared build rules: the answer is a single living
  artifact you both own; the goal is the best possible *finished product*; carry the
  **entire** current answer forward every turn; **preserve and extend** what is sound;
  **only remove or change a point if you can say why it is wrong**, and say so;
  **justify every change**; do not pad or rubber-stamp — added detail must earn its
  place; if you remove something the other model added, give the reason it fails, and
  if they later answer that reason, accept the restoration.
- `roles/builder.md` — the per-turn posture + stage postures (below).

`build_debater_system()` becomes mode-aware: build mode composes
`build_baseline.md + builder.md`; debate mode is unchanged (`baseline.md + {role}.md`).

### Build turn output: plain text + delimited changelog

Each build turn is **one `complete()` call** (plain text, *not* `complete_json`) — a
long evolving answer inside a JSON string is exactly the fragility that broke value
models earlier. The model is instructed to output:

```
<the full revised working answer>
=== CHANGES ===
- kept: …
- added: …
- challenged/removed: … (why)
```

The orchestrator splits on the `=== CHANGES ===` delimiter: text before = the new
working answer; text after = the changelog (logged, and shown to the next model). If
the delimiter is absent, treat the whole output as the new working answer with an
empty changelog (robust fallback).

### The build loop (`run_build`)

A sibling of `run_debate`:
1. **Seed** (shared): both models answer independently; the orchestrator picks the
   stronger as the **initial working answer** (reuse `seed()`; the seed turn's text is
   the starting draft).
2. For `debate_turn in 1..turn_cap`, alternating slots (non-seeding model first):
   - Active model gets: refined prompt + **current working answer** + the **previous
     turn's changelog** + its stage posture. Returns revised answer + changelog.
   - `working_answer = revised answer`; append a `Turn` (text = revised answer) so the
     transcript holds the evolution; log a `build_turn` event (working answer +
     changelog + stage).
   - Observe-only **judge** read after each turn (unchanged; reads the transcript).
     Stages advance on the existing schedule. `--judge-stop` / `--circularity-stop`
     remain available but **off by default**; the circularity detector also naturally
     fires if the working answer stops changing (a fine convergence signal).
   - **Anti-thrash:** reuse `max_stage_reversals`-style bounding — track points removed
     with a reason; the role rules plus a logged `reversal` count keep remove/restore
     loops bounded (cap = config knob, default 1, same spirit as stage reversals).
3. Return `stop_reason`, `last_read`, and the final `working_answer`.

### Present pass-through (build mode)

`present()` in build mode: `final_answer = working_answer` (verbatim). It still emits
metadata via a small `complete_json` over the **changelogs/judge read only** (never
the answer): `outcome_type` (genuine_consensus if changelogs converged to nothing
contested; productive_stalemate if a residual remains; turn_cap/circular otherwise),
`residual_disagreement`, `note_to_user`. This removes the synthesis bottleneck while
keeping the same `DebateResult` shape.

### Stages (reuse the 3-stage schedule, build postures)

`builder.md` stage postures: **Stage 1 — Draft & expand** (build the answer out fully;
add the strongest, best-supported content), **Stage 2 — Challenge & refine** (contest
weak/unsupported points with reasons; prune what fails; integrate what survives),
**Stage 3 — Finalize** (lock the answer; resolve or clearly mark any residual). Same
`--stages` knob; default 3/3/2.

### Logging

`build_turn` events carry `{index, slot, stage, working_answer, changelog}`;
transcript.md shows each turn's revised answer + changelog so the growth is visible.

## Decisions

1. **Symmetric single `builder` role** (both slots), not an asymmetric builder/critic
   pair. Matches the user's vision (each turn both preserves+extends *and*
   contests-with-reason) and avoids one slot being purely additive (bloat) or purely
   critical. Pruning pressure lives in the role rules, not in a separate critic.
   *Reversible* (could split later).
2. **Plain-text revised answer + delimited changelog**, not `complete_json` with a
   `revised_answer` string field. A multi-thousand-token answer inside JSON is the
   fragility that broke value models earlier (truncation/garble). Plain text is robust;
   the delimiter parse has an empty-changelog fallback. *Reversible.*
3. **Final answer = working answer verbatim; present is metadata-only.** This is the
   whole point — it removes the lossy re-summary. Alternative (a final polish pass) was
   rejected: it reintroduces a synthesizer and the exact confound/compression we are
   removing. *Reversible.*
4. **Reuse the 3-stage schedule** with build postures, rather than inventing a new
   schedule. Keeps `--stages`, `StageController`, and the judge working unchanged.
   *Reversible.*
5. **`Config.mode` default `"debate"`** — full backward compatibility; build mode is
   strictly additive. *Reversible.*
6. `Assumption:` the existing `complete_json` JSON-retry and the capable-orchestrator
   guidance are enough for the small metadata `present` call; the long answer never
   goes through JSON.

## Invariants

- **`mode="debate"` parity:** with mode unset/`debate`, `run()` takes the exact
  existing path (`run_debate` + `present`) and all current tests pass unchanged.
- **No detail loss at the end:** in build mode `result.final_answer` is identical to
  the last logged `working_answer` (assert in a test).
- Offline/stub CI: no test instantiates a real SDK; no new dependencies.

## Error Behavior

- Missing `=== CHANGES ===` delimiter → whole output is the new working answer, empty
  changelog (no crash).
- A build turn that returns empty/near-empty text → keep the prior working answer for
  that turn and log a `build_turn_noop` (never blank the artifact).
- Unknown `--mode` value → `argparse` choices reject it.

## Testing Strategy

**Offline (stub, CI):**
- A `BuildStubProvider` whose `complete()` returns `"<prior answer> + [turn N add]\n=== CHANGES ===\n- added: N"`,
  so the working answer provably **carries prior content + grows** each turn.
- Assert: build loop runs to `turn_cap`; each turn's working answer contains the prior
  turn's content (accumulation); `result.final_answer == last working_answer`
  (pass-through, not re-synthesized); changelog parsed; `mode="debate"` path untouched
  (existing tests still green).
- Delimiter-absent fallback and empty-turn no-op covered.

**Live (manual, later phase):** run `--mode build` on a prompt; confirm the answer
accumulates detail, stays on-topic, and the final answer equals the working answer.

## Out of Scope

- The full 3-way quality experiment (single vs adversarial vs build) — a **separate
  phase** after this lands, and it should use the better methodology discussed
  (verifiable-answer questions, controlled synthesizer, larger n, validated inputs).
- Changing the default mode; UI exposure of `--mode` (CLI/config only for now).
- A separate convergence-based stop for build mode (the turn cap + existing optional
  stops suffice for v1).
