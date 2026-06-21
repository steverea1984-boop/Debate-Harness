# Does debate beat a single model? — quality test

_Run 2026-06-19. The first experiment to measure the project's actual goal:
**better-reasoned answers**, not just outcome labels (§9, §13)._

**Bottom line:** Round 1 found debate *losing* to a single model — but that was an
artifact of the synthesis step compressing the answer (fixed in Round 2). With the
fix **and a corrected baseline** (Round 2c), the honest result is **weak and mixed**:
**same-model debate modestly beats a single model (2/3); cross-model vs. single is a
wash; same edges cross.** Not the clean "debate wins" an earlier (flawed) pass
reported. n=3 — directional only.

_Raw artifacts (answers, judge verdicts + reasons, scripts, exact setup) are in
[`repro/`](repro/) so every claim below is auditable. The present-step fix is PR #13.
Run at Steve's request to test the project's core goal. **Data-integrity note:** an
automated PR review caught that one Round 2 `single` answer was off-topic
(a model glitch); it was regenerated and the whole set re-judged on full
(untruncated) answers — those corrected numbers are the ones reported here._

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
3. **cross** — DeepSeek V3 × a *different vendor*. **The cross partner differs by
   round:** **Round 1 used Qwen2.5 72B**; **Round 2 / 2c used Llama 3.3 70B** (Qwen
   was rate-limited upstream when Round 2 ran). So cross-round comparisons of the
   *cross* arm mix two different partners — the reliable claims are *within* a round.

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
comparable to or longer than the single answers.

**Data-integrity correction (Round 2c).** A first pass at Round 2 *appeared* to show
debate winning cleanly (cross 2/3, same 2/3 vs. single). An automated PR review then
caught that the **p0 `single` answer was contaminated** — a model glitch returned
off-topic text instead of a nuclear answer — so debate had "won" p0 against a
non-answer, and the judge only saw the truncated first 3,500 chars so it never
noticed. We **regenerated that answer and re-judged all three prompts on full,
untruncated text.** The corrected verdicts:

| Comparison | Round 1 | Round 2 (flawed) | **Round 2c (corrected)** |
|---|---|---|---|
| cross vs single | single 2/3 | cross 2/3 | **wash — cross 1/3, 2 splits** |
| same vs single  | single 3/3 | same 2/3 | **same 2/3** (1 split) |
| cross vs same   | same 3/3   | 1–1 wash | **same 2/3** |

**Honest conclusion:** fixing the synthesis step *did* remove the Round 1 artifact
(debate no longer loses on length), but on clean data the evidence that **debate
beats a single model is weak and mixed**: same-model debate modestly beats single
(2/3), cross-model vs. single is a wash, and same edges cross. At **n = 3** this is
directional at best — *not* the clean "debate wins" the flawed pass suggested. The
present-step fix (PR #13) stands on its own merit (a one-paragraph synthesis of a
full debate is self-evidently poor); the inflated quality claim does not.

The natural next probe for the §9 / interaction-structure question is a different
*structure* — e.g. a **collaborative** mode (two models giving each other
constructive feedback toward a joint best answer) vs. the current adversarial
debate. Whether collaboration beats adversarial, or just reintroduces the sycophancy
the adversarial design exists to fight, is the next experiment.

## Caveats

- **n = 3 prompts, one debater pair per round, one judge model.** Directional, not
  definitive. The cross partner differs between rounds (Qwen R1, Llama R2/2c), so the
  reliable claims are *within* a round; in Round 2c that is: **same-model debate
  modestly beats single (2/3); cross-vs-single is a wash; same edges cross.**
- **Length confound drove Round 1** (where debate finals were 2–4× shorter and lost).
  It is **neutralized in Round 2/2c** — the fixed `present` step makes debate finals
  comparable in length — which is why the Round 2c numbers, not Round 1, are the
  honest read.
- The "single" answer is raw DeepSeek; the debate "final" is a `gpt-4.1-mini`
  synthesis — so this also compares two different synthesizers, not just
  debate-vs-no-debate.
- **Data integrity:** one Round 2 `single` answer was contaminated (off-topic) and
  silently inflated an earlier pass; it was caught in review, regenerated, and the
  set re-judged on full untruncated text (Round 2c). Validate that baseline answers
  are on-topic before trusting any quality tally.

_Reproduce: produce answers with a single provider call + two debates per prompt,
then blind-judge with a strong model in both orders. The debate finals come from
the orchestrator's `present` step (`debate_harness/orchestrator.py`)._
