---
name: commit
description: "Stage the intended changes and create one clear conventional commit."
user-invocable: true
argument-hint: "[optional commit message]"
---

# Commit

Create one clear Conventional Commit for the intended current changes.

## Workflow

1. Inspect `git status`, `git diff`, and `git diff --cached`.
2. Read recent commit messages for useful scopes and local phrasing.
3. If there is nothing worth committing, stop.
4. Stage only intended files.
5. Use the user's message if provided. Otherwise write a Conventional Commit message: `type(scope): subject`. Imperative subject, 72 characters or fewer, no trailing period.
6. End the message with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
7. Create the commit and report the hash and message.

## Rules

- Prefer staging specific files over broad adds. Never `git add .` in these repos — they carry untracked tooling/output junk (e.g. `tools/*-output.*`, `tmp/`).
- Do not commit `.env`, credentials, keys, or any `delivery/clients/` content.
- If the diff is not understood, stop.
- Prefer `feat`, `fix`, `refactor`, `test`, `docs`, or `chore`.
- The subject should say what changed. Add a body when the why, risk, or verification matters.
- Never bypass hooks with `--no-verify`. If a hook fails, fix the cause or stop and report.
