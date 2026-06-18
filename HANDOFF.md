# HANDOFF — Debate-Harness

A pickup guide for continuing this project in a **new session** (local or cloud).
The chat history doesn't transfer, but everything important is in the repo. Read
this plus `CLAUDE.md`, and you're oriented.

_Last updated: 2026-06-18._

---

## TL;DR — where things stand

- The **§12 minimal prototype is built and merged** to `main`: a staged,
  sequential debate between an Anthropic proposer and an OpenAI skeptic, refereed
  by an orchestrator, with an observe-only stage/consensus judge and full logging.
- **Three features shipped through the spec→implement→review→pr loop:**
  1. CI green-check (offline, no keys) — merged.
  2. State-based stage 2→3 transition (optional, gated) — merged.
  3. Structural circularity detection (optional, gated) — **open as draft PR #2**.
- **CI is green** on every push/PR (`.github/workflows/ci.yml`): byte-compile +
  25 offline tests, all runnable with no API keys.
- **Not done yet — the actual point of the prototype (§13): nobody has run a real
  debate.** Everything so far is control-flow + offline tests. The next high-value
  work is running real prompts and reading transcripts, which **needs live API
  keys** (see "What's next").

## Where the work lives

- Default branch: **`main`** (not `master` — the skills assume `master`).
- Working branch this session: `claude/confident-euler-einykg`.
- **PR #2** (draft): "Structural circularity detection" — green CI, awaiting
  review/merge. Merging is **Steve's call**; agents open PRs and stop.

## Repo map

```
roles/                  baseline.md + proposer.md + skeptic.md (debater system prompts)
orchestrator/system.md  the referee's system prompt
debate_harness/
  config.py             every knob (models, stage schedule, all feature gates)
  providers.py          Anthropic + OpenAI behind one interface (lazy SDK imports)
  transcript.py         the single shared thread + per-debater rendering
  orchestrator.py       refine -> seed -> staged loop -> present
  judge.py              observe-only stage/consensus judge
  stages.py             StageController (timer vs state-based 2->3)
  circularity.py        CircularityDetector (LLM-free restatement check)
  logging_utils.py      per-run run.json + transcript.md
  cli.py                entry point: single / stdin / --batch
.claude/skills/         the 9 ProcessSmith operating skills (auto-loaded)
docs/<feature>/spec.md  the durable design record for each feature
tests/                  offline unit tests (stub providers; no keys, no network)
prompts/sample_prompts.txt   ~10 varied prompts
CLAUDE.md               operating notes + environment adaptations
```

## How we work (the skills)

Delivery loop, all available as `/`-commands (auto-loaded from `.claude/skills/`):

```
spec -> plan -> implement -> review -> pr        (or task-to-pr from a GitHub issue)
```

`/spec` writes `docs/<slug>/spec.md` and **pauses for approval** before any code.
`/review` runs in a fresh independent context (author != reviewer). Source of
truth for the skills is the private `steverea1984-boop/processsmith-skills` repo;
locally, install them the canonical way: `npx skills add steverea1984-boop/processsmith-skills`.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env        # set ANTHROPIC_API_KEY and OPENAI_API_KEY

# offline — control-flow only, no keys needed (what CI runs)
python -m py_compile debate_harness/*.py
python -m unittest discover -s tests -v

# live — needs both keys
python -m debate_harness.cli "Should a startup default to a monolith or microservices?"
python -m debate_harness.cli --batch prompts/sample_prompts.txt
```

Each live run writes a timestamped dir under `logs/` (gitignored): `run.json`
(structured) + `transcript.md` (readable) capturing every turn, stage decision,
judge read, circularity read, and the final presentation.

## Feature gates / experiment knobs (all in `config.py`)

| Flag / config | Default | What it does |
|---|---|---|
| `--stages S1 S2 S3` | `3 3 2` | turn counts per stage = the cooling-rate knob |
| `--same-model` | off | both slots on the Anthropic model (sycophancy baseline, §9) |
| `--elaborations N` / `max_elaborations` | `0` | orchestrator elaboration requests (§8) |
| `--judge-stop` / `enable_judge_stop` | off | let a confident judge read end the debate |
| `--state-2to3` / `state_based_2to3` | off | judge drives the stage 2→3 boundary (§7) |
| `--circularity-stop` / `enable_circularity_stop` | off | stop a structurally circular debate (§10) |

Everything observe-only / off by default (spec §13): the judge and circularity
detector **watch and log** before they're trusted to drive. Tunable starting
guesses to revisit against transcripts: `stage_transition_confidence=0.6`,
`min_stage2_turns=1`, `circularity_threshold=0.6`, `circularity_min_turns=4`.

## What's next (backlog)

**Needs live API keys (the core §13 goal — do these once keys are available):**
- **Run ~10 prompts and read the transcripts.** Are the stages, postures, seed
  criteria, and arc behaving as designed? Expect at least one surprise.
- **Observe-only eval report (§13):** run the prompts, compare the judge's
  perceived stage / consensus reads against your own read — is the judge
  trustworthy before it drives?
- **Same- vs cross-model baseline (§9, open Q4):** does cross-model earn its keep?

**Offline / no keys (fine to do in cloud):**
- Merge PR #2.
- Richer report output (a per-run markdown summary / comparison across runs).
- Config from a file (beyond env vars + CLI flags).
- More / harder sample prompts.

Open questions to hold these against are listed in `README.md` ("Open questions
this prototype is built to probe").

## Environment adaptations

The skills were written for a local workstation (`gh` CLI, `master` default). This
repo has run in **Claude Code on the web**, so:

| Skill assumes | Substitute |
|---|---|
| `gh` CLI | **GitHub MCP tools** (`mcp__github__*`) — no `gh` in the web container |
| default branch `master` | **`main`** — branch from / target `origin/main` |
| `~/.codex/...`, local tokens | not present in the web container; use MCP connectors |

**Cloud session limits encountered:** no API keys (can't run live debates unless
you add `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` as environment secrets); GitHub
access scoped to this repo; ephemeral container (commit/push to keep anything);
no `send_later` (can't self-schedule check-ins).

## Continuing locally vs in cloud

- **Going local** (recommended for the next phase): clone the repo, set both keys
  in `.env`, and you can immediately run live debates and read transcripts — the
  thing cloud is blocking. `gh` works; the skills work as written.
- **Staying in cloud:** add `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` as environment
  secrets and this same setup runs live; you keep the wired-in MCP connectors.

Either way: a fresh session reading `CLAUDE.md` + this file + the `docs/*/spec.md`
records picks up with full project context. The conversation doesn't carry over;
the artifacts do.
