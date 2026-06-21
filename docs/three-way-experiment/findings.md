# Three-way experiment: single vs debate vs build (rubric-scored)

_Run 2026-06-21. The rigorous version of "does the harness beat a single model?",
built to fix the methodology flaws of the earlier goal experiment._

## Methodology (the upgrades)

The earlier goal experiment used a **subjective** "which answer is better?" judge on
opinion questions — noisy, and it rewarded length. This run fixes that:

- **Rubric-based scoring, not holistic.** Each of 4 knowledge-rich questions has a
  **fixed rubric** of ~8 key points a complete, correct answer should cover (written
  before scoring). A blind judge (Claude Sonnet 4.6) grades **each rubric point
  independently**: covered = yes (1.0) / partial (0.5) / no (0), and flags any point
  the answer gets **factually wrong**. Score = coverage fraction. This is far more
  objective than a vibe, and it rewards *both* breadth (build's strength) and
  correctness (debate's strength).
- **Input validation:** every one of the 12 answers was confirmed on-topic before
  scoring (the contamination lesson from last time).
- **Conditions:** `single` (DeepSeek V3 alone, comprehensive prompt), `debate`
  (DeepSeek × Llama 3.3 70B, adversarial mode), `build` (same two, build mode).
  Referee `gpt-4.1-mini`, stages 2/2/1.
- **Questions:** SQL vs NoSQL tradeoffs; causes of the 2008 crisis; LLM-app security
  risks; monolith vs microservices tradeoffs.

## Results

Rubric coverage (key points covered / 8), 0 factual errors flagged in any answer:

| Question | single | debate | build |
|---|---|---|---|
| SQL vs NoSQL | 100% | 69% | 100% |
| 2008 crisis | 100% | 81% | 100% |
| LLM-app security | 31% | 19% | **38%** |
| monolith vs micro | 94% | 75% | 75% |
| **average** | **81%** | **61%** | **78%** |
| avg length (chars) | 4,399 | 3,121 | 7,686 |

## Findings

### 1. Neither multi-model mode beats a single strong model on coverage.
**single (81%) ≥ build (78%) > debate (61%).** Just asking one capable model to be
comprehensive is a strong, cheap baseline. The harness's machinery did not produce a
*more complete* answer than that.

### 2. Debate (as built) actively *hurts* comprehensiveness.
Debate scored lowest on every question and produced the shortest answers (3,121 chars
avg). This is the **synthesis-compression** problem in action: the `present` step
re-summarizes the exchange and sheds rubric points. ~20 coverage points lost vs single.
(Build mode's verbatim pass-through was designed to avoid exactly this — and it does:
build never compresses.)

### 3. Build *matches* single but doesn't exceed it — despite ~2× the length.
Build's answers are far longer (7,686 vs 4,399 chars) but cover the **same** key points
as single, not more. The extra length is deeper elaboration on the same points, not
additional coverage. So build doesn't *hurt* (unlike debate) but its accumulation
didn't buy more breadth here.

### 4. The one exception points to where build *can* win.
On **LLM-app security** — the only question where a single model fell well short of the
rubric (31%), i.e. the only one with real *headroom* — **build led (38%) > single (31%)
> debate (19%)**. When a question genuinely has many distinct points a single model
under-covers, build's accumulation helped. The other three questions hit a **ceiling**:
single was already at 94–100%, leaving nothing for build to add.

## Honest caveats (what this does and doesn't show)

- **The metric measures breadth, not depth or quality-per-point.** Rubric coverage
  rewards hitting the key points; it does **not** capture whether build's 2× length is
  *better-reasoned, better-organized, or more useful per point*. Build may produce a
  better *product* in ways this metric can't see — "best possible product" is partly a
  depth/quality question, and this run only measured coverage.
- **Ceiling effect.** 3 of 4 questions were "easy" enough that single already scored
  ~100%, so debate/build had no room to beat it. A fairer test needs **harder,
  higher-headroom questions** (like the security one) where a single model genuinely
  under-covers.
- **Synthesizer confound.** The three finals are written differently (single = raw
  DeepSeek; debate = gpt-4.1-mini synthesis; build = the builders' verbatim text), so
  this isn't a perfectly clean debate-vs-no-debate comparison.
- **n = 4, one judge, one model set.** Directional, not definitive.

## Takeaways

1. **Debate mode's compression is a real, measured liability** for comprehensive
   answers — build mode's verbatim pass-through is the right fix, and a less-compressive
   `present` would help debate mode too.
2. **Build is a "safe upgrade":** at least as complete as a single model, never worse,
   and better when a question has many distinct points to cover. But it is **not** a
   free win — it's ~2× the tokens for equal-or-slightly-better breadth.
3. **The value case for the harness is narrow and unproven on quality.** To find where
   multi-model genuinely wins, the next test should use **high-headroom, multi-point
   questions** and a metric that captures **depth/quality per point**, not just breadth
   — possibly verifiable-answer reasoning tasks where error-correction (debate's
   theoretical strength) is objectively measurable.

_Artifacts in [`repro/`](repro/): the 4 answer sets (single/debate/build), the
produce + score scripts, and the full per-item judge output._
