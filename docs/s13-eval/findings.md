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

Two explanations were initially entangled:
- (a) Claude genuinely writes sharper, more debate-provoking openings, and the
  criterion correctly selects them; or
- (b) the Claude orchestrator has a same-vendor stylistic affinity.

**Resolved by the orchestrator probe (run 2026-06-18).** The same three prompts
were re-run with the **orchestrator + judge switched to `gpt-5.5`**, debaters
unchanged (Claude proposer vs gpt-5.5 skeptic). A gpt-5.5 referee **still seeded
the Claude answer 3/3**, with the same rationale (Claude = "clearer, more
argumentative thesis"; gpt-5.5 = "broader and more cautious"). A different-vendor
referee — the one that would carry any same-vendor pull *toward* the gpt-5.5
debater — agreeing rules out (b) and lands on **(a): Claude genuinely writes the
sharper seed under this criterion, and the criterion selects it regardless of who
judges.**

| Orchestrator | Debaters | Claude answer seeded |
|---|---|---|
| Claude | cross (Claude = proposer) | 3/3 |
| Claude | swap (Claude = **skeptic**) | 3/3 |
| gpt-5.5 | cross (Claude = proposer) | 3/3 |

The effect tracks the **Claude model** (seeded whether proposer or skeptic, and
under either referee vendor), not the orchestrator's vendor or the slot. The seed
criterion is behaving as designed — it selects for a sharp, contestable thesis,
not for correctness — and Claude's opening style matches that criterion more often
than gpt-5.5's. Still n = 3 prompts; a larger prompt set would firm this up.

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

- **n = 3 per condition.** Signals, not conclusions — including the seed result,
  which is consistent across referee vendors but still over only three prompts.
- Single schedule (3/3/2), observe-only throughout. The orchestrator probe adds a
  second referee vendor (gpt-5.5) but otherwise holds these fixed.

## Recommended next probes

1. ~~**OpenAI orchestrator**~~ — **done** (see finding 1): resolved finding 1 as a
   genuine model-style effect, not orchestrator vendor-bias.
2. **Harder / more prompts** where the two models should genuinely diverge, to
   give finding 3 (cross vs. same) a fair test at the content level. Now the
   highest-value open probe.
3. **More n** before treating the seed result as established.

_Reproduce: `python -m debate_harness.cli --no-clarify "<prompt>"` for CROSS;
`--same-model` for SAME; SWAP needs a custom `Config` (OpenAI proposer / Anthropic
skeptic). Live runs need both API keys; needs the utf-8 fix (PR #3) on Windows and
the `max_completion_tokens` fix (PR #4) for the GPT-5 series._
