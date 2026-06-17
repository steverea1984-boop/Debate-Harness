---
name: branch
description: "Create a traceable Git branch for the current task."
user-invocable: true
argument-hint: "<branch-name or task reference>"
---

# Branch

Create a traceable Git branch for the current task.

## Workflow

1. Inspect the current branch, `git status`, and available task context.
2. Learn the repo's convention from existing branch names: prefixes like `feat/` or `fix/`, ticket placement, casing. Follow it. (ProcessSmith/OpenClaw convention: `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `docs/<issue>-<slug>`.)
3. Choose the name. A user-provided name wins as given. Otherwise derive `<issue-number>-<short-kebab-summary>` when the work has a GitHub issue, or `<short-kebab-summary>` when it does not: lowercase summary of five words or fewer, strip anything that is not a letter, digit, or hyphen.
4. Branch from the up-to-date default branch (`master` here): fetch, then create from `origin/master`. Branch from anywhere else only when the user explicitly asks to stack.
5. If the branch already exists, switch to it and report how it relates to master, including any commits it already carries. Otherwise create and switch.
6. Report the branch name, its base, and any uncommitted work that was already present.

## Rules

- Stop if the working tree state makes switching branches unsafe.
- Do not overwrite or discard uncommitted work.
- Include the issue number for work from a GitHub issue.
- Do not invent issue numbers.
