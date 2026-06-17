# ProcessSmith Skills

The canonical operating skills for every agent in Steve's system — **Claude Code, Codex,
and OpenClaw/Jimmy**. This repo is the single source of truth for *how we work*; the
project repos (`processsmith-systems`, `openclaw-workspace`) carry only repo-specific
facts in their `CLAUDE.md`/`AGENTS.md`, plus `docs/WORKFLOW.md` (the process standard)
and `REVIEW.md` (review concerns).

Adapted from [owainlewis/blueprint](https://github.com/owainlewis/blueprint) —
cherry-picked and customized for our GitHub-issues + ClickUp + multi-agent setup.

## Install / sync

```bash
npx skills add steverea1984-boop/processsmith-skills
```

Or copy `skills/<name>/SKILL.md` into your agent's skills directory
(Claude Code on Windows: `~/.claude/skills/<name>/SKILL.md`).
Re-sync after any merge to this repo.

## The skills

| Skill | Purpose |
|---|---|
| `spec` | Technical design before code; pauses for Steve's approval |
| `plan` | Break a spec/brief into agent-sized tasks |
| `implement` | One scoped change: smallest complete, tested, verified |
| `review` | Pre-merge review — fresh independent context, evidence-backed, blockers first |
| `task-to-pr` | The delivery loop: issue → branch → implement → review → pr |
| `branch` / `commit` / `pr` | Mechanical steps, standardized |
| `clickup-standards` | ClickUp structure, attachment formats, safe-write rules |

## Changing how we work

**Every change to this repo is a pull request.** Edit a skill → branch → PR → review →
Steve merges → all agents re-sync. The PR history is the changelog of our operating
system: why a rule exists is findable forever.

Keep it thin (Blueprint's discipline): skills encode **process**, not knowledge.
Reference material lives in the project repos or the knowledge base. If a skill grows
past what an agent can hold in its head, split or cut it.
