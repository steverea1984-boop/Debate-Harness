# Value-model comparison — first findings

_Run 2026-06-18, via the new OpenRouter per-role model selection. Goal: can
**mid-tier value models** (not Opus/GPT-5.5) run useful debates, and does
cross-model still beat a same-model baseline? Maintains the §13 end goal._

## Setup

- **Debaters (value models, via OpenRouter):**
  - `cross-ds-qwen`: DeepSeek V3 (proposer) × Qwen2.5 72B (skeptic)
  - `cross-llama-gem`: Llama 3.3 70B × Gemini 2.5 Flash
  - `same-ds`: DeepSeek V3 × DeepSeek V3 (same-model baseline)
- **Orchestrator + judge:** `gpt-4.1-mini` (see finding 1 for why this matters).
- **Schedule:** 2/2/1 (turn cap 5), observe-only.
- **Prompts:** _p0 nuclear_ (is nuclear necessary to decarbonize the grid, or can
  renewables+storage do it alone — a hard, genuinely contested empirical question)
  and _p1 language_ (should a growing eng team standardize on one language).

## What broke first (and why it's the headline)

The debaters were never the problem — **the orchestrator/judge roles were.** They
are the only ones that must emit structured JSON (refine, seed-selection, the
per-turn judge read, present), and value models stress that path two ways:

1. **JSON parse failures.** `claude-3.5-haiku` via OpenRouter intermittently
   returned truncated or *degenerate* JSON (`"needs_clarclarclarification"`);
   `gemini-2.5-flash`, a *thinking* model, spent its budget on reasoning and
   truncated the judge JSON. Either crashed the whole debate. **3 of 6** debates
   failed this way on the first pass.
2. **Semantic failure that still parses.** Worse, `claude-3.5-haiku` returned an
   **empty refined prompt**, and the harness fell through to an empty question —
   so the debate unmoored and the model **hallucinated entirely off-topic content**
   (community policing, UBI, surveillance — on a *nuclear power* prompt). This
   parsed fine; only reading the transcripts caught it.

Two harness fixes resulted (in the web-UI PR):
- **Retry the in-prompt JSON path** (`complete_json`, up to 3× with a firmer
  "minified, short values" instruction) — a single re-roll almost always recovers.
- **Coalesce an empty refined prompt to the raw prompt** in both refine paths.

With both fixes and a capable orchestrator, the same matrix ran **6/6 clean and
on-topic**.

## Findings (clean run, gpt-4.1-mini orchestrator)

| Prompt | Condition | Seed | Outcome | Judge trajectory* |
|---|---|---|---|---|
| p0 nuclear | cross-ds-qwen   | A | turn_cap_no_convergence | d d d d d |
| p0 nuclear | cross-llama-gem | B | turn_cap_no_convergence | d d d d d |
| p0 nuclear | same-ds         | A | productive_stalemate    | d d d d S |
| p1 language| cross-ds-qwen   | A | genuine_consensus       | d d d d C |
| p1 language| cross-llama-gem | B | genuine_consensus       | d d d d C |
| p1 language| same-ds         | A | genuine_consensus       | d d d d C |

\* per-turn judge `consensus_shape`: `d`=disagreement, `C`=genuine_consensus,
`S`=productive_stalemate. All six finals were verified on-topic with substantive,
coherent residuals (e.g. "nuclear's firm capacity + upfront cost vs. the feasibility
and timeline of breakthrough storage").

### 1. Orchestrator model quality is the critical variable — more than the debaters.
A debater only writes prose; the **orchestrator** refines the prompt, selects the
seed, and writes the final presentation. A weak orchestrator (`claude-3.5-haiku`
here) poisons the whole run regardless of how good the debaters are. `gpt-4.1-mini`
(≈$0.40/$1.60 per Mtok) handled it cleanly. **Practical rule: spend your model
budget on the orchestrator/judge first; the debaters can be cheaper.**

### 2. Value-model debaters produce genuinely useful debates.
DeepSeek V3, Qwen2.5 72B, Llama 3.3 70B and Gemini 2.5 Flash all argued coherently
and on-topic, with the judge tracking a real arc. The premium tier is not required
to get a useful debate out of this harness.

### 3. Prompt difficulty drives convergence more than the pairing does.
The softer prompt (p1) reached `genuine_consensus` under **all three** pairings;
the hard empirical prompt (p0) reached it under **none**. The harness reflects real
difficulty rather than manufacturing agreement.

### 4. Cross vs. same: no clear winner at this n.
On the hard prompt, both cross-model pairs stayed in open disagreement to the turn
cap (`ddddd`), while the same-model pair crystallized a clean `productive_stalemate`
(`ddddS`) — weakly suggestive that cross-model surfaces more unresolved friction,
but the residuals are substantively similar and n is tiny. No support here for "cross
clearly beats same"; needs more prompts.

### 5. The `gpt-4.1-mini` judge read cleanly and monotonically.
Trajectories were stable (`ddddd`, `ddddC`, `ddddS`) with **no early-consensus
flicker** — unlike the Opus §13 runs, where the judge twice flagged a confident
`genuine_consensus` that then reverted. Either gpt-4.1-mini is steadier or less
sensitive; worth watching before trusting `--judge-stop`.

## Caveats

- **n = 1 per (prompt × condition)**, 2 prompts, one orchestrator model. Signals, not
  conclusions — especially finding 4.
- Outcome labels are coarse; a content-level comparison of residual quality across
  pairings is the natural next step.

## Recommended next steps

1. **More prompts / repeats** with the validated `gpt-4.1-mini`-orchestrator setup to
   give cross-vs-same (finding 4) a fair test.
2. **Sweep orchestrator models** (gpt-4.1-mini vs gemini-2.5-pro vs a premium anchor)
   — finding 1 says this is the highest-leverage knob.
3. Consider a tiny **JSON-mode / structured-output** path for OpenRouter models that
   support it, to reduce reliance on the retry.

_Reproduce via the web UI (per-role pickers) or the CLI, e.g.:_
`python -m debate_harness.cli --no-clarify --stages 2 2 1 --slot-a openrouter:deepseek/deepseek-chat-v3-0324 --slot-b openrouter:qwen/qwen-2.5-72b-instruct --orchestrator openrouter:openai/gpt-4.1-mini "<prompt>"`
