---
name: task-to-pr
description: "Turn one GitHub issue into a reviewed PR. Use when the user passes an issue reference (e.g. 'ps#1', 'openclaw-workspace#56', an issue URL) and expects code, tests, review, and a PR. Use implement when no PR is expected."
user-invocable: true
argument-hint: "<issue reference> e.g. ps#1, openclaw-workspace#56, or an issue URL"
---

# Task To PR

Turn one GitHub issue into a reviewed PR, the standard ProcessSmith/OpenClaw delivery loop. The user supplies the issue; do not hunt for work. Treat the issue as the audit trail.

## Workflow

1. **Resolve the issue.** Fetch it with `gh issue view`. Capture the problem, acceptance criteria (definition of done), linked context, and any PR policy. Comment that work has started. **Stop and report** if the issue is unclear, already has an open PR for the same work, spans unrelated changes, or needs decisions/secrets it does not answer — that means it fails the Definition of Ready (see the SOP) and needs a `/spec` first.
2. **Decide the entry point** (SOP three-question test): if the issue has open design decisions, run `/spec` and stop for Steve's approval before coding. Otherwise continue.
3. **Run `branch`** from a clean tree off `origin/master`.
4. **Run `implement`** with the issue as the task. Acceptance criteria are the definition of done.
5. **Run `review` with a fresh independent subagent** (author ≠ reviewer). Give it the diff + the issue's acceptance criteria + a scope-creep check. Judge every finding, fix the valid in-scope ones, re-verify against the live system where relevant.
6. **Run `pr`.** Body includes the issue link, acceptance-criteria status, verification evidence, and any "Deploy steps (human)".
7. **Update the issue** with the PR link and evidence (a comment).
8. **For ClickUp-linked client work**, also update the engagement task per `clickup-standards` (attachments PDF/DOCX/XLSX/images only).
9. **Report:** issue, branch, commit, PR URL, verification run, anything blocked or unverified.

## Boundaries

- One issue, one branch, one PR.
- **Pause at the opened PR. Merging is always Steve's decision** (admin bypass). Do not merge.
- Open the PR only after verification has run, or state clearly what could not be verified.
- On a blocker an agent can't resolve, comment what blocked you on the issue, apply `needs:human`, and exit cleanly rather than guessing.
