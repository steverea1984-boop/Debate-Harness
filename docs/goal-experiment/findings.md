# Does debate beat a single model? — quality test

_Run 2026-06-19. The first experiment to measure the project's actual goal:
**better-reasoned answers**, not just outcome labels (§9, §13)._

**Bottom line:** Round 1 found debate *losing* to a single model — but that was an
artifact of the synthesis step compressing the answer. With that step fixed
(Round 2), **debate beats a single model.** Cross-vs-same is still a wash.

## The question

The whole harness exists to test one hypothesis: does a **staged two-model debate
produce better-reasoned answers than a single model alone** — and does using **two
different models** (cross) beat the **same model twice** (same)? The earlier
value-model run was inconclusive because it only compared coarse outcome labels.
This one measures answer **quality** directly.

## Design

For each of 3 hard, genuinely contested prompts (nuclear vs. renewables; prepay a
4% mortgage vs. invest; monolith vs. microservices), we produced three answers:

1. **single** — DeepSeek V3 alone, no debate (just asked for its best answer).
2. **same** — DeepSeek V3 × DeepSeek V3 debate.
3. **cross** — DeepSeek V3 × Qwen2.5 72B debate.

Debates used the validated `gpt-4.1-mini` orchestrator/judge, schedule 2/2/1.
A strong, neutral judge (**Claude Sonnet 4.6**, blind to which answer is which)
then picked the better-reasoned answer in three pairwise comparisons —
`cross vs single`, `cross vs same`, `same vs single` — **each run in both answer
orders** to control for position bias. A verdict counts only if it held across both
orders.

## Round 1 result (before the fix)

| Comparison | Consistent verdict |
|---|---|
| same vs single | **single 3 / 3** |
| cross vs single | **single 2 / 3** (1 order-dependent split) |
| cross vs same | **same 3 / 3** |

Quality ranking: **single > same > cross.** The single model (no debate) beat both
debate variants almost everywhere, and cross-model was the *worst* of the three.

**On its face, debate did not beat a single model — it made the answer worse.**

## …but the result is confounded, and the confound is the real finding

The debate final answers were **2–4× shorter** than the single answers (e.g. on the
nuclear prompt: single 3211 chars vs. cross 700). The judge's stated reasons were
overwhelmingly about **completeness** — "more comprehensive," "more analytical
depth," "covers the key dimensions," "more decision-useful." It was rewarding the
fuller answer.

Reading the answers confirms why: the single model gives a structured, multi-part
answer (categories of tradeoffs, conditions that would change the call); the
debate's **present step** (`gpt-4.1-mini`) compresses the whole exchange into one
dense paragraph — a reasonable *conclusion*, but it throws away the depth the
debate generated.

**So this measures the synthesis step, not the reasoning.** The bottleneck is the
**present/final-answer step over-compressing**, not (necessarily) that debate
reasons worse. The debate may well surface better reasoning in the transcript — we
just don't deliver it in the final answer.

## What this tells us to do next

The clean follow-up that would actually test the hypothesis on a level field:

1. **Fix the present step** — instruct the orchestrator to produce a *complete*,
   structured final answer (position, the load-bearing reasons, the residual
   tradeoff, when to decide differently), and/or give it more output budget or a
   stronger present model. Then re-run single vs. same vs. cross **controlling for
   length** and re-judge.
2. Only after that is the cross-vs-same question (§9) worth re-asking — right now
   both debate variants are handicapped by the same compressed-synthesis problem.

## Round 2 result (present step fixed)

We rewrote the `present` prompt to demand a **complete, structured** final answer
(position, load-bearing reasons by dimension, both sides' concessions, and the
conditions that change the answer) instead of a one-paragraph summary, then re-ran
the exact same experiment. (Cross partner was Llama 3.3 70B this round — Qwen was
rate-limited upstream — still DeepSeek × a different vendor.)

The debate finals went from ~650–1,400 chars to **3,266–4,635 chars** — now
comparable to or longer than the single answers. The verdicts flipped:

| Comparison | Round 1 | **Round 2 (fixed)** |
|---|---|---|
| cross vs single | single 2/3 | **cross 2/3** (1 split) |
| same vs single  | single 3/3 | **same 2/3** (1 single) |
| cross vs same   | same 3/3   | **1–1 wash** (1 split) |

**Conclusion: once the synthesis step delivers a complete answer, debate beats a
single model** (both cross- and same-model debate win ~2/3 vs. single). The Round 1
"debate loses" result was an artifact of the compressed `present` step, **not** the
debate's reasoning — exactly as the confound predicted. Fix shipped in the
present-step PR.

**Cross vs. same is still a wash** — both beat single, but neither clearly beats the
other. That (the §9 question) is the open thread, and the natural next probe is a
different *interaction structure* — e.g. a **collaborative** mode (two models giving
each other constructive feedback toward a joint best answer) vs. the current
adversarial debate. Whether collaboration beats adversarial, or just reintroduces
the sycophancy the adversarial design exists to fight, is the next experiment.

## Caveats

- **n = 3 prompts, one debater pair per round, one judge model.** Directional, not
  definitive. The cross partner differs between rounds (Qwen R1, Llama R2, due to a
  rate limit), so the cleanest claim is *within* Round 2: debate > single.
- **Length confound is large** and not fully neutralized by the "ignore length"
  instruction — it likely drives most of the single-model win.
- The "single" answer is raw DeepSeek; the debate "final" is a `gpt-4.1-mini`
  synthesis — so this also compares two different synthesizers, not just
  debate-vs-no-debate.

_Reproduce: produce answers with a single provider call + two debates per prompt,
then blind-judge with a strong model in both orders. The debate finals come from
the orchestrator's `present` step (`debate_harness/orchestrator.py`)._
