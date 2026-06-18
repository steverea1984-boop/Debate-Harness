# §13 observe-only evaluation — first live debates

_Run 2026-06-18. The first real transcripts the prototype was built to produce
(spec §13). Observe-only: every gate off, turn-cap stop only._

## Setup

- **Debaters:** `claude-opus-4-8` and `gpt-5.5`. **Orchestrator + judge:** always
  `claude-opus-4-8`.
- **Schedule:** default 3/3/2 (turn cap 8), `--no-clarify`.
- **Prompts (3):** _finance_ (pay off a 4% mortgage early vs. invest the
  difference), _ethics_ (use AI-generated art commercially without disclosure),
  _testing_ (high unit coverage vs. fewer broad integration tests).
- **Conditions (3 × 3 = 9 debates):**
  | Condition | Slot A (proposer) | Slot B (skeptic) |
  |---|---|---|
  | **CROSS** (default §9) | `claude-opus-4-8` | `gpt-5.5` |
  | **SAME** (§9 baseline) | `claude-opus-4-8` | `claude-opus-4-8` |
  | **SWAP** (vendor↔role) | `gpt-5.5` | `claude-opus-4-8` |

  SWAP is a custom config used only to isolate vendor from role; not a CLI flag.

## Results

| Cond | Prompt | Seed | Outcome | 1st judge `should_stop` | consensus trajectory* |
|---|---|---|---|---|---|
| CROSS | finance | **A** (claude) | genuine_consensus | read 2 → **reverted** | d C d d C C C C |
| CROSS | ethics  | **A** (claude) | genuine_consensus | read 5 (held) | d d d d S C C C |
| CROSS | testing | **A** (claude) | genuine_consensus | read 5 (held) | d C d S C C C C |
| SAME  | finance | B | genuine_consensus | read 4 (held) | d d d C C C C C |
| SAME  | ethics  | A | genuine_consensus | read 4 (held) | d d d S C C C C |
| SAME  | testing | B | genuine_consensus | read 5 (held) | d d d C C C C C |
| SWAP  | finance | **B** (claude) | genuine_consensus | read 5 (held) | C d d S C C C C |
| SWAP  | ethics  | **B** (claude) | genuine_consensus | read 5 (held) | d d d d C C C C |
| SWAP  | testing | **B** (claude) | genuine_consensus | read 4 (held) | d d d S C S C C |

\* per-turn judge `consensus_shape`: `d`=disagreement, `C`=genuine_consensus,
`S`=productive_stalemate. (A short 1/1/1 smoke run on monolith-vs-microservices
also seeded the claude proposer and reached genuine_consensus.)

## Findings (against the open questions)

### 1. Seed selection is confounded with model identity — the orchestrator seeded the **Claude** answer in 6/6 cross-vendor debates. (Q1)
In **CROSS** the seed was always slot A (Claude proposer); in **SWAP**, with the
vendors switched between slots, it flipped to always slot B — i.e. **still the
Claude answer**, now in the skeptic slot. The **SAME** control (both Claude) was
mixed (A, B, B), as expected when there is no vendor to prefer.

So the preference tracks **vendor, not slot/role**. But the orchestrator's stated
reasoning is consistently *quality/debate-value* framed, and it consistently
characterises the **gpt-5.5** seed as "thorough, well-organized, but **safer /
lands softly / restates the conventional case**" and the **Claude** seed as
"**sharper, more contestable**, does more structural work to provoke engagement."
The seed criterion explicitly rewards "a sharp, committed, contestable thesis"
over "an exhaustive but hedged one."

Two explanations remain entangled and **cannot be separated from this data**:
- (a) Claude genuinely writes sharper, more debate-provoking openings, and the
  criterion correctly selects them; or
- (b) the Claude orchestrator has a same-vendor stylistic affinity.

This matters because "seed with the **stronger** answer" is then confounded with
"seed with the **Claude** answer." **Decisive next probe: run with an OpenAI
orchestrator.** If the seed flips to favouring gpt-5.5, it's orchestrator-vendor
affinity (b); if it still favours Claude, it's a genuine style/criterion effect (a).

### 2. The judge's consensus read is unstable early — `--judge-stop` would have misfired. (Q3)
The CROSS-finance judge set `should_stop=True` with `genuine_consensus`
(confidence 0.78) at **read 2**, then the debate **reverted to open disagreement
for two more turns** before genuinely converging. With `--judge-stop` on at face
value, that debate stops early on a consensus that wasn't real. Several other runs
show the same early flicker (a `C` at read ≤2 then back to `d`). First stops that
landed at **read ≥4 all held**. **Keep `--judge-stop` off**; the read is not yet
trustworthy to drive stopping. The observe-only decoupling (§13) did exactly its
job — it caught the false positive without acting on it.

### 3. Cross-model did not out-diverge the same-model baseline (preliminary). (Q4)
**All 9 debates reached `genuine_consensus`** — including SAME-model. On these
three prompts, cross-model produced no more residual disagreement or stalemate at
the *outcome* level than same-model, so §9's "cross-model earns its keep" is **not
visible here**. Caveat: outcome label is coarse; the *content* of the residuals
may still differ. Needs harder prompts and a content-level comparison, not just
outcome tallies.

### 4. Stage-perception is steadier than consensus-perception.
The judge's `perceived_stage` tracks the 3/3/2 schedule cleanly even while its
`consensus_shape` flickers. Stage-detection looks closer to trustworthy than
consensus-detection — mild support for exploring `--state-2to3` ahead of
`--judge-stop`.

### 5. Convergence looks *earned*, not capitulation. (Q5)
Residuals are real, not papered over (finance left the taxable-only
risk-adjustment seam explicitly open; testing recorded what each model conceded).
That argues against the cooling schedule degenerating into a capitulation
schedule — though finding 3 means this still deserves a deliberate
genuine-consensus-vs-capitulation human read.

## Caveats

- **n = 3 per condition, one orchestrator vendor.** Signals, not conclusions —
  especially the 6/6 seed result, which is striking but small.
- Single schedule (3/3/2), single judge model, observe-only throughout.

## Recommended next probes

1. **OpenAI orchestrator** — the decisive test for finding 1 (vendor affinity vs.
   genuine style). Highest value.
2. **Harder / more prompts** where the two models should genuinely diverge, to
   give finding 3 (cross vs. same) a fair test at the content level.
3. **More n** before treating the seed-bias signal as established.

_Reproduce: `python -m debate_harness.cli --no-clarify "<prompt>"` for CROSS;
`--same-model` for SAME; SWAP needs a custom `Config` (OpenAI proposer / Anthropic
skeptic). Live runs need both API keys; needs the utf-8 fix (PR #3) on Windows and
the `max_completion_tokens` fix (PR #4) for the GPT-5 series._
