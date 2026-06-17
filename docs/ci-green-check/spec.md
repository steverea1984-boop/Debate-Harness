# Spec: CI green-check workflow

## What

Add a GitHub Actions workflow that runs on every push and pull request and gives
the repo a real green check **without any API keys**. It does two things: byte-
compiles the `debate_harness` package, and runs a committed offline test that
drives the full orchestrator loop with stub providers. This turns the ad-hoc
inline smoke test (run by hand during the prototype build) into a permanent
regression guard and gives PR #1 — and every future PR — a verifiable status.

## Context

- The harness control flow (refine → seed → staged alternation → observe-only
  judge after every turn → present, with full logging) was verified once during
  the build via an inline heredoc against stub providers. Nothing re-runs it, so
  a regression in `orchestrator.run_debate`, the stage schedule
  (`config.stage_for_turn`), seeding, alternation, or transcript rendering would
  go uncaught.
- Real model calls need `ANTHROPIC_API_KEY` + `OPENAI_API_KEY`, which CI must not
  hold. The good news: the loop is testable offline. Provider SDK imports are
  **lazy** — `AnthropicProvider`/`OpenAIProvider` import their SDKs inside
  `__init__` (`debate_harness/providers.py`), so importing the package needs no
  third-party packages, and a stub provider never triggers those imports.
- Relevant code: `debate_harness/orchestrator.py` (the loop + `make_provider`
  call sites), `debate_harness/config.py` (`stage_for_turn`, `turn_cap`),
  `debate_harness/judge.py`, `debate_harness/transcript.py`,
  `debate_harness/logging_utils.py`.
- Environment: default branch is `main`; this is Claude Code on the web.

## Requirements

1. A workflow at `.github/workflows/ci.yml` triggers on `push` and
   `pull_request`.
2. CI passes with **no secrets configured** — it must never require or read
   `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, and must make no network calls.
3. CI runs `python -m py_compile` over every module in `debate_harness/` and
   fails on any syntax error.
4. CI runs a committed offline test that exercises the full orchestrator loop
   end-to-end with stub providers and asserts the control-flow invariants below.
   The test is also runnable locally with a single stdlib command.
5. The test asserts, for a known stage schedule:
   - total turns = `1 (seed) + config.turn_cap`;
   - the stage sequence matches `config.stage_for_turn` for each turn (seed = 1);
   - speakers strictly alternate after the seed, starting with the non-seeding
     slot;
   - a `run.json` and a `transcript.md` are written to a logs directory.
6. The test makes **zero** network calls and instantiates **no** real provider
   (no `anthropic` / `openai` import at runtime).
7. The workflow completes in well under a minute on a standard GitHub runner.

## Design

### Files

- **`.github/workflows/ci.yml`** (new) — the workflow.
- **`tests/__init__.py`** (new, empty) — make `tests` a package.
- **`tests/test_offline_loop.py`** (new) — the offline smoke test, using stdlib
  `unittest`.

### The test

`tests/test_offline_loop.py` replaces the brittle `__new__` bypass used in the
build with a clean seam: it monkeypatches `debate_harness.orchestrator.make_provider`
to return a single `StubProvider` for all three call sites (orchestrator/judge,
slot A, slot B), then constructs `Orchestrator(cfg)` through its **real**
`__init__`. One stub class implements both methods of the `Provider` interface:

- `complete(system, messages, max_tokens)` → returns a short deterministic line
  (e.g. `"[stub turn N]"`); used for debater turns and seed answers.
- `complete_json(system, user, schema, max_tokens)` → branches on the schema's
  property names and returns a valid object for each orchestrator/judge call:
  refine (`refined_prompt`), seed selection (`seed_slot`), judge read
  (`perceived_stage`/`consensus_shape`/`should_stop=False`), elaboration
  (`request_elaboration=False`), and present (`outcome_type` etc.).

The test sets a small explicit schedule (e.g. `stage1/2/3 = 2/2/1`), runs
`orch.run("Should X or Y?")`, and asserts the invariants in Requirement 5 against
the returned `DebateResult.transcript`. Log artifacts are written under the
repo's `logs/` (gitignored); the test points `RunLogger` at a temp dir or asserts
the files exist and then leaves them (CI is ephemeral). **Default:** write to a
`tempfile.TemporaryDirectory` by passing a logger constructed against it, to keep
the workspace clean and the assertion precise.

Local run: `python -m unittest discover -s tests` (no third-party deps).

### The workflow

```yaml
name: CI
on: [push, pull_request]
jobs:
  control-flow:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Byte-compile the package
        run: python -m py_compile debate_harness/*.py
      - name: Offline control-flow test
        run: python -m unittest discover -s tests -v
```

No `pip install` step: neither `py_compile` nor the stub test needs third-party
packages (SDK imports are lazy; `dotenv` is guarded by try/except in
`config.py`). This keeps CI hermetic and immune to SDK version drift.

## Decisions

- **No dependency install in CI.** *Chosen* because the tested paths need only
  the stdlib (lazy SDK imports, guarded `dotenv`). *Alternative:* `pip install -r
  requirements.txt` for realism. *Why not:* it adds time and couples a control-
  flow check to SDK releases for no extra coverage — the SDKs are never exercised
  offline. *Reversible:* yes (add a step later, e.g. for a future import-smoke of
  the real providers).
- **stdlib `unittest`, not `pytest`.** *Chosen* to avoid adding a test dependency
  for one test (smallest safe change). *Reversible:* yes; switching to pytest
  later is mechanical.
- **Monkeypatch `make_provider` rather than bypass `__init__`.** *Chosen* so the
  test exercises the real `Orchestrator`/`Debater`/`Judge` construction path.
  *Alternative:* the `__new__` bypass used during the build. *Why not:* it skips
  real init and rots when init changes. *Reversible:* yes.
- **Triggers `on: [push, pull_request]`.** *Chosen* so feature branches and PRs
  both show checks (PR #1 needs the `pull_request` event). *Trade-off:* a PR
  branch runs both events (minor duplication). *Reversible:* yes.
- **Python matrix `3.11` + `3.12`.** *Chosen:* `3.11` matches the dev container;
  `3.12` guards forward-compat. *Reversible:* yes (add `3.13`).
- `Assumption:` the repo has GitHub Actions enabled (default for public repos).
- `Assumption:` the harness keeps two debater slots both constructed via
  `make_provider` in `Orchestrator.__init__`; if that construction path changes,
  the test's monkeypatch seam must move with it.

## Versions

- `actions/checkout@v4`, `actions/setup-python@v5` — current major-tag releases;
  pinning to the major tag is GitHub's recommended practice.
- Python `3.11`, `3.12` via `setup-python`.
- `ubuntu-latest` runner.

## Invariants

- CI never needs secrets and never hits the network — verify by confirming the
  workflow has no `env:` secrets and no step makes API calls.
- The offline test imports no real provider SDK — verify the run succeeds in a
  clean env where `anthropic`/`openai` are not installed.
- Control-flow invariants (turns, stages, alternation, logging) hold — verified
  by the test assertions themselves.

## Error Behavior

- A syntax error → `py_compile` step fails the job.
- A broken loop invariant → a failing assertion fails the job with a clear diff.
- A stub returning an object that no longer matches a schema → surfaces as a
  `ProviderError`/`KeyError` in the test, signalling that an orchestrator schema
  changed and the stub (and possibly the test) needs updating.

## Testing Strategy

- The workflow *is* the test harness; correctness is proven by it going green on
  the PR.
- Locally: `python -m py_compile debate_harness/*.py` and
  `python -m unittest discover -s tests -v` both pass.
- Negative check (manual, optional): temporarily break `stage_for_turn` and
  confirm the test fails.

## Out of Scope

- Any test that calls real Anthropic/OpenAI endpoints (needs secrets; separate
  future workflow, likely manual-dispatch only).
- Linting/formatting/type-checking (ruff/black/mypy) — could be a later job.
- Coverage measurement and reporting.
- Branch protection / required-status configuration (a repo setting, Steve's
  call, not a code change).
- Testing the observe-only judge's *judgment quality* (that's the separate §13
  evaluation feature).
