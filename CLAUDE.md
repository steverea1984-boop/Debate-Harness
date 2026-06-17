# CLAUDE.md — Debate-Harness

Operating notes for agents working in this repo. Read this first.

## What this project is

A harness that orchestrates a **staged, sequential debate between two AI models**
(an Anthropic proposer vs an OpenAI skeptic) refereed by an orchestrator, with an
observe-only consensus/stage judge. See `README.md` for the design and usage, and
the source design spec for the rationale. This is the §12 *minimal prototype* —
built to learn from transcripts, not to ship.

## How we work (ProcessSmith skills)

This repo carries the canonical ProcessSmith operating skills under
`.claude/skills/<name>/SKILL.md` (source of truth: the private
`steverea1984-boop/processsmith-skills` repo — changes there flow via PR). They
load automatically in Claude Code. The delivery loop:

```
spec  →  plan  →  implement  →  review  →  pr        (or task-to-pr end-to-end)
```

- **`/spec`** — technical design before code; writes `docs/<feature-slug>/spec.md`
  and **pauses for Steve's approval**. Use for anything with real decisions.
- **`/plan`** — break a spec into agent-sized, independently executable tasks.
- **`/implement`** — one scoped change: smallest complete, tested, verified.
- **`/review`** — pre-merge review in a **fresh independent context** (author ≠
  reviewer), evidence-backed, blockers first.
- **`/branch` `/commit` `/pr`** — the standardized mechanical steps.
- **`/task-to-pr`** — the full loop driven from one GitHub issue.
- **`/clickup-standards`** — ClickUp structure/attachment/safe-write rules.

**Merging is always Steve's decision.** Agents open PRs (draft by default here)
and stop. Never merge.

## Environment adaptations (Claude Code on the web)

The skills were written for a local workstation with the `gh` CLI and a `master`
default branch. This repo runs in the web/remote environment, so substitute:

| Skill assumes | Here, use instead |
|---|---|
| `gh` CLI (`gh issue view`, `gh pr ...`) | **GitHub MCP tools** (`mcp__github__*`). No `gh` is installed. |
| default branch `master` | default branch is **`main`** — branch from and target `origin/main`. |
| `~/.codex/...`, `processsmith-systems/tools/` paths | not present in this container; use MCP connectors directly. |
| ClickUp via Zapier SDK / local token | the **native ClickUp MCP connector** (the skill's preferred path) is available. |

Other environment facts:
- The container is **ephemeral** — commit and push anything worth keeping.
- GitHub access is **scoped to this repo** (`steverea1984-boop/debate-harness`).
  Other repos require adding to the session.
- This is a managed remote environment; outbound network is governed by the
  session's network policy.

## Running / testing the harness

```bash
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY and OPENAI_API_KEY

# control-flow smoke test (no API keys needed) — see README for the stub harness
python -m py_compile debate_harness/*.py

# a real run (needs keys)
python -m debate_harness.cli "Should a startup default to a monolith or microservices?"
python -m debate_harness.cli --batch prompts/sample_prompts.txt
```

Live model calls need both API keys. Default debaters: Anthropic
`claude-opus-4-8` (proposer) vs OpenAI `gpt-4o` (skeptic); orchestrator + judge on
Anthropic. All knobs live in `debate_harness/config.py`.

## Conventions

- Smallest safe change that fully solves the task; match existing patterns.
- Don't commit `.env`, keys, or `logs/` (gitignored — they're working artifacts).
- Stage intended files explicitly; avoid `git add .`.
