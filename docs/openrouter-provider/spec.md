# Spec: OpenRouter provider + per-role model selection

## What

Add **OpenRouter** as a third model provider and make **all four debate endpoints**
— slot A, slot B, orchestrator, and judge — **independently selectable by provider
+ model** via environment variables and CLI flags. This lets a run keep an
expensive model where it matters (e.g. Opus as proposer) while routing the
high-frequency, lower-stakes calls (the judge fires every turn) to a cheap model
through one OpenRouter key. Defaults are unchanged: a run with no new settings
behaves exactly as today.

## Context

`claude-opus-4-8` on the direct Anthropic API is expensive, and the harness leans
on it hard. Per default 3/3/2 debate the orchestrator/judge model is called ~11
times (1 refine + 1 seed-pick + 8 judge reads + 1 present) and the proposer slot
~5 times — and **today the judge always reuses the orchestrator's provider
instance**, so it can't be cheapened on its own. Routing orchestrator+judge to a
cheap model is the single biggest cost lever.

OpenRouter (`https://openrouter.ai/api/v1`) is **OpenAI-SDK-compatible** — same
client, just a different `base_url` + key — and proxies Anthropic, OpenAI, Google,
Llama, etc. behind `vendor/model` slugs. The user has an `OPENROUTER_API_KEY`
(already in `.env`).

Relevant code:
- [providers.py](../../debate_harness/providers.py) — `Provider` (base; in-prompt
  `complete_json`), `AnthropicProvider` (native messages + native json_schema),
  `OpenAIProvider` (chat.completions, sends `max_completion_tokens`),
  `make_provider(provider, model)`.
- [config.py](../../debate_harness/config.py) — `SlotConfig(provider, model, role)`,
  `slot_a`/`slot_b`, `orchestrator_provider`/`orchestrator_model`; models from env.
- [orchestrator.py](../../debate_harness/orchestrator.py) `Orchestrator.__init__` —
  builds debaters from slots; `Judge(self.orch, …)` **reuses the orchestrator
  provider**.
- [judge.py](../../debate_harness/judge.py) `Judge(provider, max_tokens)` — calls
  `provider.complete_json(...)`. Splitting the judge needs only a separate provider
  instance passed here.
- [tests/test_providers.py](../../tests/test_providers.py) — CI installs **no deps**
  and is stub-only; tests inject a fake `openai` module rather than instantiating a
  real SDK client.

## Requirements

1. A new `openrouter` provider reaches any OpenRouter-hosted model using the
   `openai` SDK against `https://openrouter.ai/api/v1` with `OPENROUTER_API_KEY`.
2. `make_provider("openrouter", model)` returns it; unknown providers still raise.
3. Each of the four endpoints — `slot_a`, `slot_b`, `orchestrator`, `judge` — is
   independently configurable `(provider, model)` via env vars **and** CLI flags.
4. The **judge** is constructed from its own `(provider, model)`; when unset it
   **defaults to the orchestrator's** provider+model (today's behavior).
5. **Backward compatible:** with no new env/flags, `Config()` and a normal run
   produce byte-identical provider/model assignments to current `main`. The legacy
   env vars (`ANTHROPIC_MODEL`, `OPENAI_MODEL`, `ORCHESTRATOR_MODEL`) keep working.
6. OpenRouter `complete_json` uses the base in-prompt-JSON path (no assumption of
   native json_schema across routed models). The Anthropic **native** structured
   path is used only for direct `provider=="anthropic"`.
7. Existing tests stay green; new offline tests cover the OpenRouter wiring and the
   judge split. CI requires no new dependencies.

## Design

### Provider layer (`providers.py`)

Add `OpenRouterProvider` as a thin subclass of `OpenAIProvider`:

```python
class OpenRouterProvider(OpenAIProvider):
    vendor = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, model: str):
        Provider.__init__(self, model)          # skip OpenAIProvider's default client
        from openai import OpenAI               # lazy import (offline/stub-safe)
        import os
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        self._client = OpenAI(base_url=self.BASE_URL, api_key=key)

    def complete(self, system, messages, max_tokens):
        full = [{"role": "system", "content": system}, *messages]
        resp = self._client.chat.completions.create(
            model=self.model, messages=full, max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
```

- **Token param = `max_tokens`** (not `max_completion_tokens`). OpenRouter documents
  `max_tokens` and normalizes per backend; it is the broadly-compatible choice
  across the many models a slug may route to. `complete` is overridden (rather than
  inherited) for exactly this one-line difference.
- `complete_json` is **inherited from `Provider`** (in-prompt JSON + `_extract_json`),
  same path `OpenAIProvider` already uses for the orchestrator/judge/seed/present
  schemas — already validated live this session.

`make_provider` gains:
```python
if provider == "openrouter":
    return OpenRouterProvider(model)
```

### Config layer (`config.py`)

Add an `orchestrator`/`judge` `SlotConfig`-style pair and a resolver that reads env
with this **precedence (highest first): CLI flag → per-role env var → legacy env
var → hardcoded default.** CLI is applied in `cli.py` (below); `Config` resolves
env + defaults.

Four endpoints, each `(provider, model)`:

| Endpoint | provider default | model default (legacy env) | new per-role env |
|---|---|---|---|
| slot A | `anthropic` | `ANTHROPIC_MODEL` → `claude-opus-4-8` | `SLOT_A_PROVIDER`, `SLOT_A_MODEL` |
| slot B | `openai` | `OPENAI_MODEL` → `gpt-4o` | `SLOT_B_PROVIDER`, `SLOT_B_MODEL` |
| orchestrator | `anthropic` | `ORCHESTRATOR_MODEL` → `claude-opus-4-8` | `ORCHESTRATOR_PROVIDER` (+ existing `ORCHESTRATOR_MODEL`) |
| judge | = orchestrator | = orchestrator | `JUDGE_PROVIDER`, `JUDGE_MODEL` |

- Add fields `judge_provider` / `judge_model`. In `__post_init__` (or a small
  resolver), if judge provider/model are unset, copy them from
  `orchestrator_provider`/`orchestrator_model`. This preserves "judge == orchestrator"
  by default.
- Keep `slot_a`/`slot_b` as `SlotConfig`; their `provider`/`model` now also honor the
  new `SLOT_A_*`/`SLOT_B_*` env vars (legacy `ANTHROPIC_MODEL`/`OPENAI_MODEL` remain
  the model fallback so nothing breaks).
- `to_dict()` already serializes config into `run.json`; judge fields ride along, so
  every run records exactly which model played each role.

### Orchestrator (`orchestrator.py`)

One change: build the judge from its own provider.
```python
self.judge = Judge(
    make_provider(config.judge_provider, config.judge_model),
    config.orchestrator_max_tokens,
)
```
(When judge defaults to orchestrator's provider+model this is behavior-identical to
today, just a second instance instead of a shared one.)

### CLI (`cli.py`)

Add four optional flags, each taking a `provider:model` string (`:` separator —
provider names never contain `:`, and OpenRouter slugs use `/`, which is preserved):

```
--slot-a PROVIDER:MODEL
--slot-b PROVIDER:MODEL
--orchestrator PROVIDER:MODEL
--judge PROVIDER:MODEL
```

Example (cheap referee, Opus proposer kept):
```
python -m debate_harness.cli --no-clarify \
  --judge openrouter:anthropic/claude-3.5-haiku \
  --orchestrator openrouter:anthropic/claude-3.5-haiku \
  "Should a startup default to a monolith or microservices?"
```

`--same-model` keeps its current meaning. A flag overrides the corresponding env.
Malformed values (no `:`) → `parser.error(...)`.

### `.env.example` + `README.md`

- `.env.example`: add `OPENROUTER_API_KEY=` and a commented block documenting the
  four per-role provider/model env vars and the `vendor/model` slug format.
- `README.md`: a short "Choosing models / cost" subsection — the provider table, the
  cheap-judge example, and the note that the judge defaults to the orchestrator.

## Decisions

1. **OpenRouter token param = `max_tokens`.** Alternatives: reuse
   `max_completion_tokens` (what the direct OpenAI path now sends). OpenRouter's
   documented field is `max_tokens` and it normalizes per backend, so `max_tokens`
   is safest across arbitrary routed slugs. Reversible (one line).
2. **OpenRouter as a subclass of `OpenAIProvider`, not a rewrite.** Only the client
   construction and the token param differ; subclassing keeps it DRY and matches the
   existing thin-provider pattern. Reversible.
3. **Judge defaults to the orchestrator's provider+model.** Alternative: give the
   judge its own hardcoded default. Defaulting to the orchestrator preserves exact
   current behavior and the "one referee model" mental model unless the user opts to
   split. Reversible.
4. **`provider:model` CLI syntax with `:` separator.** Alternative: two flags per
   role (`--judge-provider`/`--judge-model`) — eight flags, noisier. `:` is
   unambiguous because OpenRouter slugs use `/`, not `:`. Reversible.
5. **Precedence CLI → per-role env → legacy env → default.** Standard
   specific-overrides-general ordering; keeps every existing `.env` working. Reversible.
6. `Assumption:` OpenRouter is reachable from this environment and the user's key has
   credit. If a call fails, it surfaces as the SDK's normal error (same as the
   OpenAI path) — no new error handling introduced.

## Invariants

- **Default-config parity:** with no new env/flags set, the resolved
  `(provider, model)` for all four endpoints equals current `main`
  (anthropic/`claude-opus-4-8` proposer, openai/`gpt-4o` skeptic,
  anthropic/`claude-opus-4-8` orchestrator **and** judge). Guard with a test that
  asserts the resolved tuples.
- **Offline/stub CI:** no test instantiates a real SDK client; CI installs no deps.
- All existing tests remain green.

## Testing Strategy

**Offline (CI, no deps, no network):**
- `OpenRouterProvider` wiring: inject a fake `openai` module (as `test_providers.py`
  does); assert `OpenAI(...)` is constructed with `base_url=".../api/v1"` and the key
  from `OPENROUTER_API_KEY`, and that `complete` sends **`max_tokens`** (not
  `max_completion_tokens`). Assert `ProviderError` when the key is missing.
- `make_provider("openrouter", …)` returns an `OpenRouterProvider`.
- Config resolution: (a) default config → the four expected `(provider, model)`
  tuples (parity invariant); (b) `JUDGE_PROVIDER`/`JUDGE_MODEL` unset → judge mirrors
  orchestrator; (c) per-role env + CLI override precedence.
- CLI parse: `--judge openrouter:anthropic/claude-3.5-haiku` resolves to
  `("openrouter", "anthropic/claude-3.5-haiku")`; malformed value errors.

**Live (manual, user's key):** run one debate with `--orchestrator` and `--judge`
on a cheap OpenRouter model, debaters unchanged; confirm it completes, writes a
clean transcript, and `run.json` config shows the per-role models. Optionally a
fully-OpenRouter run (all four roles) to confirm the in-prompt JSON path holds for a
non-OpenAI backend.

## Out of Scope

- Per-call price tracking / budgeting / cost reporting.
- Automatic model fallback or OpenRouter routing preferences.
- Streaming responses.
- Native structured-output for OpenRouter backends (in-prompt JSON is sufficient and
  already proven).
