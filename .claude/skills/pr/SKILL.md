---
name: pr
description: "Commit, push, and open a pull request with a clear description. Use when finished work on the current branch needs to become a PR."
user-invocable: true
argument-hint: "[optional: PR title, base branch, or draft|ready]"
---

# PR

Take the finished change on the current branch to an open pull request.

## Workflow

1. Run `branch` first if still on `master`.
2. Run `commit` for any uncommitted intended changes.
3. Push the branch.
4. Open the PR with `gh`. Title like a commit subject — these repos squash-merge, so the title becomes the commit on `master`.
5. Write the body from the diff and the work actually done, not from memory: what changed and why, the GitHub issue link (`Closes #N`), tests/checks run with results, review findings fixed, and anything not verified. Include a **"Deploy steps (human)"** section when the change needs live config (env vars, secrets, dashboard settings) and a one-paragraph **"Lesson"** when there's a reusable takeaway. A reviewer should be able to judge the change without reading the conversation.
6. Report the PR URL.

## Rules

- One PR per branch. If one is already open, push and update its description instead of opening another. Preserve human edits to the body.
- Do not claim verification that did not run. Verify against the live system where relevant, not just the merged artifact.
- Open as draft only if asked; otherwise normal PR — Steve (or the `@reviewer` agent) reviews, then Steve merges via admin bypass.
- If push or PR creation fails, keep the branch and commit local and report the exact failure.
