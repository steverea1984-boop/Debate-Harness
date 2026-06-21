# Debate-Harness

A harness that orchestrates a **staged, sequential debate between two AI models**
to produce better answers than either model would give alone. One model argues as
the **proposer**, the other as the **skeptic**; an **orchestrator** referees —
refining the prompt, seeding the debate, naming the active stage each turn, and
presenting the result. An **observe-only judge** watches alongside and logs what
it thinks is happening without steering.

This is the **minimal prototype** described in the design spec (§12): fixed models,
fixed roles, a three-stage schedule on a turn-based timer, single shared thread,
basic seed step, and full logging — built to *learn from real transcripts*, not to
ship. See `debateharnessspec.md`-equivalent design notes for the full rationale.

## What's here

```
roles/
  baseline.md        # universal debater rules (always-on layer)
  proposer.md        # proposer overlay + its stage postures
  skeptic.md         # skeptic overlay + its stage postures
orchestrator/
  system.md          # the referee's system prompt
debate_harness/
  config.py          # every knob (models, stage schedule, intervention caps)
  providers.py       # Anthropic + OpenAI behind one interface
  transcript.py      # the single shared thread + per-debater rendering
  judge.py           # observe-only consensus/stage judge (§10, §13)
  orchestrator.py    # refine → seed → staged loop → present
  logging_utils.py   # per-run run.json + transcript.md
  cli.py             # command-line entry point
prompts/
  sample_prompts.txt # ~10 varied prompts to run through it
```

The three instruction layers from the spec map directly onto the files:
1. **Orchestrator system prompt** → `orchestrator/system.md`
2. **Static role files** → `roles/baseline.md` + `roles/{proposer,skeptic}.md`
3. **Dynamic per-turn injection** → built in `transcript.render_for(...)` (the
   orchestrator *names* the active stage each turn; the role file is the single
   source of truth for what that stage means).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # then fill in your keys
```

Set credentials (env vars or `.env`):

- `ANTHROPIC_API_KEY` — required (Anthropic debater slot + orchestrator + judge).
- `OPENAI_API_KEY` — required (OpenAI debater slot).
- `OPENROUTER_API_KEY` — optional; one key to reach many vendors via OpenRouter.

By default the two debaters are **different vendors** (spec §9 — cross-model
addresses both sycophancy *and* shared blind spots):

| Slot | Provider  | Default model        | Role      | Model env (legacy) |
|------|-----------|----------------------|-----------|--------------------|
| A    | Anthropic | `claude-opus-4-8`    | proposer  | `ANTHROPIC_MODEL`  |
| B    | OpenAI    | `gpt-4o`             | skeptic   | `OPENAI_MODEL`     |

The orchestrator and the observe-only judge default to Anthropic
(`ORCHESTRATOR_MODEL`, default `claude-opus-4-8`; the judge mirrors the
orchestrator). Every endpoint's **provider and model** can be changed — including
to OpenRouter — see [Choosing models / cost](#choosing-models--cost) below.

### Choosing models / cost

All four endpoints — **slot A, slot B, orchestrator, judge** — are independently
selectable by `provider` + `model`. Provider is `anthropic`, `openai`, or
`openrouter` (OpenAI-SDK-compatible; one key reaches Anthropic/OpenAI/Google/Llama/
etc. as `vendor/model` slugs). Pick via env vars (`SLOT_A_PROVIDER`/`SLOT_A_MODEL`,
`SLOT_B_*`, `ORCHESTRATOR_PROVIDER`, `JUDGE_PROVIDER`/`JUDGE_MODEL`) or CLI flags.
**Defaults are unchanged**, and the **judge mirrors the orchestrator** unless set
separately.

Cost note: the judge runs after *every* turn, so it dominates per-debate calls.
Routing it (and the orchestrator) to a cheap model is the biggest lever:

```bash
python -m debate_harness.cli --no-clarify \
  --orchestrator openrouter:anthropic/claude-3.5-haiku \
  --judge openrouter:anthropic/claude-3.5-haiku \
  "Should a startup default to a monolith or microservices?"
```

### Web UI

A local web UI to compose debates (per-role model picker), watch them run live,
read transcripts, and **compare two runs side by side** — handy for value-model
comparison experiments.

```bash
pip install -r requirements-web.txt
python -m debate_harness.web        # then open http://127.0.0.1:8000
```

It reuses the same engine and the incremental `run.json`/`transcript.md` logging
(debates run on a background thread; the page polls for live progress). Tip: keep
a capable model on the **orchestrator** (it refines, seeds, and presents) and on
the **judge** — note that *thinking* models can truncate the judge's JSON.

## Usage

```bash
# Single prompt (interactive — the orchestrator may ask you clarifying questions)
python -m debate_harness.cli "Should a startup default to a monolith or microservices?"

# Read the prompt from stdin
echo "Is nuclear necessary to decarbonize the grid?" | python -m debate_harness.cli -

# Batch over a file (one prompt per line; never asks clarifying questions)
python -m debate_harness.cli --batch prompts/sample_prompts.txt
```

Useful flags:

| Flag | Effect |
|------|--------|
| `--mode debate\|build` | Interaction mode. `debate` (default) = adversarial proposer vs skeptic, answer synthesized at the end. `build` = **cumulative shared answer**: both slots use one *builder* role and revise a single growing working answer each turn; the **final answer is that built artifact verbatim** (no re-synthesis). See `docs/build-mode/spec.md`. |
| `--no-clarify` | Skip clarifying questions even in interactive mode. |
| `--stages S1 S2 S3` | Turn counts per stage (default `3 3 2`). This is the **cooling-rate** knob (open question §2). |
| `--judge-stop` | Let a *confident* judge read end the debate early (default: observe-only, turn-cap only). |
| `--state-2to3` | Let the judge's read drive the **stage 2→3** transition instead of the timer (gradual + reversible + turn-capped; §7). Default off. |
| `--circularity-stop` | Stop early when the debate is **structurally circular** — debaters restating themselves (§10). A cheap, no-AI lexical check; default off (observe-only, logged each turn). |
| `--same-model` | Run **both** slots on the Anthropic model — the sycophancy baseline (§9) to measure cross-model against. |
| `--slot-a` / `--slot-b` / `--orchestrator` / `--judge` | Override an endpoint's model as `PROVIDER:MODEL` (e.g. `--judge openrouter:anthropic/claude-3.5-haiku`). See **Choosing models / cost**. |
| `--elaborations N` | Allow up to N orchestrator elaboration requests (default `0`). |

Every run writes a timestamped directory under `logs/`:

- `run.json` — structured record of the config, refined prompt, both seed answers,
  the seed selection + reasoning, every turn (with stage), **every observe-only
  judge read**, any interventions, the stop reason, and the final presentation.
- `transcript.md` — the same thing as a readable narrative.

`logs/` is gitignored — these are working artifacts for reading, per the spec's
testing discipline.

## How the loop works (spec §3, §6, §7)

1. **Refine.** The orchestrator rewrites the raw prompt into a debate-ready one
   (asking clarifying questions first if interactive and the prompt is vague).
2. **Seed.** Both debaters answer the refined prompt independently; the orchestrator
   picks the stronger answer to seed the shared thread and hands it to the other
   model.
3. **Sequential debate.** The non-seeding model responds; then turns strictly
   alternate in one shared thread. Each turn is tagged with a stage from the
   schedule:
   - **Stage 1 — Surface & stress** (hot: surface every weakness)
   - **Stage 2 — Work the disagreements** (pursue the survivors to resolution)
   - **Stage 3 — Resolve** (converge with a reason, or name the tradeoff)

   The schedule cools on a **turn-based timer** (default 3/3/2). The 1→2 boundary
   is intentionally turn-based ("have we found *all* the weaknesses?" is
   near-unfalsifiable), and the spec's preferred 2→3 state-detection is left to a
   later phase — here the judge only *observes*.
4. **Judge (observe-only).** After every turn an LLM judge logs the stage it
   *perceives* and the consensus shape it sees (`disagreement`,
   `genuine_consensus`, `capitulation`, `productive_stalemate`, `circular`) — the
   §13 discipline of decoupling judgment from action so you can check whether the
   read can be trusted before letting it drive.
5. **Stop.** At the turn cap (or early, only with `--judge-stop`).
6. **Present.** The orchestrator surfaces the consensus answer, the clean residual
   tradeoff, or a flagged non-convergence — without ever taking a side.

## Design choices worth knowing

- **The orchestrator acts on *form*, never *content*** (§8). It can flag a claim as
  unsupported or vague; it never says which side is right. Elaboration is capped and
  off by default precisely because asking a model to expand point A but not B is
  itself a directional nudge.
- **Roles distort the models on purpose** (§7) to fight the trained-in tendency to
  capitulate. Stage 3 says "converge *with reason* or name the tradeoff" — never
  "agree" — to keep the cooling schedule from becoming a capitulation schedule.
- **Observe-only by default** (§13). The whole system's value rests on an LLM
  judging whether two LLMs agree, which can be wrong in the same ways the debaters
  are. So the judge watches first; you read transcripts and decide if it's
  trustworthy before flipping `--judge-stop`.

## Open questions this prototype is built to probe

Carried straight from the spec — read the logs against these:
1. Are the seed-selection criteria right, and do they differ from final-answer quality?
2. How fast should the schedule cool? (`--stages` is the knob.)
3. How reliable is the observe-only stage/consensus judgment vs. your own read?
4. Does cross-model actually beat the `--same-model` baseline on hard prompts?
5. Are the baseline / overlay / stage-posture wordings producing reasoning or theatre?

## Limitations (by design, for v1)

No file/repo attachment, no tool calls, no UI, no sophisticated consensus-driven
stopping, no parallel execution. These are deliberately out of scope until the core
loop is validated (spec §2, §11, §12).
