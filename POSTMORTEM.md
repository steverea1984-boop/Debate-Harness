# Debate-Harness — Postmortem & Lessons

**Status: concluded (2026-06-21).** The harness is built, tested, and works. The
experiments it was built to run gave a clear, honest answer to the question it
existed to ask — and that answer is the reason we're stopping. This document keeps
what's worth keeping: what we learned about model performance, multi-agent
structure, experiment methodology, and engineering. The code remains as a reference
implementation.

---

## 1. The verdict (why we're stopping)

**Question:** does a staged debate / collaborative build between two models produce
*better answers* than a single strong model alone?

**Answer, across two independent rigorous experiments:** **no.** A single strong
model is as good or better than the multi-model modes — every time.

| Test (objective metric) | single | debate | build |
|---|---|---|---|
| Knowledge coverage (rubric %, n=4) | **81%** | 61% | 78% |
| Verifiable reasoning (accuracy, n=8) | **100%** | 88% | 100% |

- **Debate consistently *underperforms*** — it compresses answers (losing detail) and
  in one reasoning case **turned a correct single-model answer into a wrong one**
  (clock angle: single said 7.5°, the debate machinery produced 82.5°).
- **Build matches single** but never meaningfully beats it, at ~2× the tokens. Its
  one edge was on the single question with real headroom (LLM-app security: build 38%
  vs single 31%).

**Why it doesn't help (and won't):** strong 2026 models **don't make the errors
debate exists to catch, and don't have the coverage gaps build exists to fill.** On
any question with a knowable answer that we could readily construct, the single model
already nailed it (a "ceiling effect" we hit in *three* separate experiments). The
multi-model machinery adds cost, latency, and *risk* (it can corrupt a right answer)
for no measurable gain. That's a structural reason, not a tuning problem.

---

## 2. Model performance (what we observed)

All via OpenRouter unless noted. Costs are approximate $/Mtok (in/out).

### The single biggest finding: value models are excellent
**DeepSeek V3** (~$0.20/$0.77) as a lone model scored **8/8 on hard reasoning** and
**81% rubric coverage on knowledge questions** — beating or matching the entire
multi-model apparatus. The expensive frontier models (Claude Opus 4.8, GPT-5.5)
were **not needed** for good answers.

### Referee reliability is the real differentiator — not the debaters
The demanding role is the **orchestrator/judge** (it must emit structured JSON:
refine, seed-selection, per-turn judge reads, present). A reliability sweep split the
catalog:

- **Referee-safe** (clean structured output): `gpt-4.1-mini`, `gpt-4o`,
  `llama-3.3-70b`, `deepseek-v3`, `qwen-2.5-72b`, `claude-sonnet-4.6` (+ the premium
  `claude-opus-4-8`, `gpt-5.5`).
- **Debater-only** (failed as referee): `claude-3.5-haiku` (returned an *empty* refined
  prompt → the debate unmoored into off-topic hallucination), `gemini-2.5-flash` /
  `gemini-2.5-pro` (*thinking* models — reasoning ate the token budget and **truncated
  the JSON**), `mistral-medium-3.1`.

**Practical rule:** spend your model budget on the orchestrator/judge first; the
debaters can be cheaper. A weak referee poisons the whole run regardless of how good
the debaters are.

### Concrete model gotchas worth remembering
- **Thinking models are risky for structured JSON** — they truncate it when reasoning
  consumes the output budget. Don't use them where a strict JSON object is required.
- **Model IDs are case-sensitive lowercase** (`gpt-5.5`, not `GPT-5.5` → 404).
- **GPT-5 series rejects `max_tokens`** — needs `max_completion_tokens`.
- **Free OpenRouter routes rate-limit** (Qwen via DeepInfra returned 429s mid-run).
- Even capable models occasionally emit **truncated or degenerate JSON**; a single
  retry recovers almost always (we added one).

### Cost reality
The **entire value-model effort cost ~$1.33** on OpenRouter (dozens of debates + a
strict grader). The expensive part was the early premium runs on the *direct*
Anthropic/OpenAI APIs (Opus 4.8 + GPT-5.5), estimated **$15–40** (couldn't be queried
from here). Lesson: route to value models; reserve frontier models for where they
demonstrably matter (which, per §1, was nowhere here).

---

## 3. Multi-agent structure (what we learned about the design)

- **Adversarial debate has two measured failure modes:** (a) the `present`/synthesis
  step compresses the exchange 2–4× and sheds content; (b) the back-and-forth can
  *introduce* an error a single pass didn't have.
- **Build mode** (cumulative shared answer, final = the artifact verbatim) fixes (a)
  by design — answers grow instead of compressing — but accumulation only buys quality
  when there's genuine coverage headroom, which strong models rarely leave.
- **The observe-only judge is not trustworthy to drive stopping** — `--judge-stop`
  would have misfired on early, confident-but-wrong "consensus" reads that later
  reverted.
- **Seed selection tracks model *style*, not vendor bias** — the orchestrator
  consistently seeded Claude's draft; a *different-vendor* (gpt-5.5) orchestrator did
  the same, ruling out same-vendor favoritism (it's that Claude writes sharper seeds).
- **Convergence ≠ quality.** Debates reliably reached "genuine consensus," but
  consensus shape told us nothing about whether the answer was good.

---

## 4. Methodology lessons (the most reusable part)

These cost us two retracted headlines. They're the real takeaways for any future
model-comparison work:

1. **Measure the right thing.** Outcome labels (consensus/stalemate) were useless.
   *Rubric coverage* and *verifiable correctness* gave real signal. A subjective
   "which answer is better?" LLM judge is noisy and **rewards length** — it nearly
   produced a false "debate wins" result.
2. **Validate inputs before scoring.** A *contaminated* baseline answer (off-topic,
   from a model glitch) once inflated a whole result. Always check answers are
   on-topic first.
3. **Don't truncate the judge's view** — truncation hid the contamination above.
4. **Control confounds:** length (debate lost on *brevity*, not reasoning) and
   synthesizer (single vs debate are written by different models).
5. **Beware ceiling effects.** If the single model already scores ~100%, you learn
   nothing. Pick *high-headroom* questions — we hit ceilings three times before
   accepting the answer.
6. **Judge in both answer orders** to cancel position bias.
7. **n matters; don't overclaim before the data is clean.** Tiny samples + one bad
   data point swung the headline twice. The honest result needed the corrections.

---

## 5. Engineering & process lessons

- **Stacked PRs are a trap.** Twice, a PR based on a feature branch never reached
  `main` (the base got squash-merged, so merging the child folded it into a dead
  branch — GitHub still labeled it "MERGED"). **Branch every PR off `main`; rebase,
  don't stack. And verify file *contents* on `main` after a merge — never trust the
  label.**
- **Long unattended background jobs die when the machine sleeps.** We lost ~13 hours
  (then again) to overnight sleep killing experiment runs. Run experiments inside an
  active window, or use a scheduler that survives the app.
- **Adversarial review of your own work genuinely helps** — ironically, the one place
  "debate" paid off was the *process*: an automated PR-reviewer agent caught a
  contaminated data artifact and a non-adversarial-mode bug that the author missed.
- Cross-platform basics bite: **Windows cp1252** crashed file writes until pinned to
  utf-8; the harness still lacks **transient-error (429) retry** (a known gap).

---

## 6. What was built (kept as reference)

A complete, working harness, all on `main`, 54 offline tests green:

- Staged two-model **debate** mode and cumulative-answer **build** mode (`--mode`).
- **OpenRouter** provider + **per-role model selection** (slot A/B, orchestrator,
  judge each independently chosen) — the cost lever that made experimentation ~free.
- A **web UI** (compose / live run / compare) and a curated, **referee-tagged** model
  catalog.
- Observe-only stage/consensus **judge** and structural **circularity** detector.
- Reproducible **experiment artifacts + findings** under `docs/` (the §13, value-model,
  goal, 3-way, and reasoning experiments — every claim auditable).

---

## 7. If anyone ever revisits

The only place multi-agent might pay off is **genuinely frontier-hard tasks** where
even the best models fail often (hard competition math, novel multi-step reasoning,
agentic tool-use error-correction). Even there, **cheaper techniques usually win**
(let the model think longer; sample it a few times and majority-vote). The bar for a
*debate harness* to beat "one strong model + a good prompt + maybe self-consistency"
is high and getting higher as models improve. Build on this code only with a
concrete, verified task where a single strong model is measurably unreliable — not
for general question-answering.

— *Concluded after a thorough, honest run. The answer wasn't the hoped-for one, but
it's a true one, and knowing it is worth more than a product built on a false
premise.*
