# Reproducibility artifacts — goal experiment

Raw artifacts behind [`../findings.md`](../findings.md), so the reported rankings
can be audited.

## Setup (both rounds)

- **Prompts (3):** nuclear vs. renewables; prepay a 4% mortgage vs. invest;
  monolith vs. microservices. (Verbatim text is inside `produce.py` and the
  `round2-answers-*.json` files.)
- **single** = DeepSeek V3 alone (one provider call, no debate).
- **same** = DeepSeek V3 × DeepSeek V3 debate.
- **cross** = DeepSeek V3 × **Qwen2.5 72B (Round 1)** / **Llama 3.3 70B (Round 2)**.
  (Qwen was rate-limited upstream in Round 2, hence the swap — see findings caveat.)
- **Orchestrator + judge** for debates: `openrouter:openai/gpt-4.1-mini`; **stages 2/2/1**.
- **Quality judge:** `openrouter:anthropic/claude-sonnet-4.6`, blind, run in **both
  answer orders**; a verdict counts only if it holds across both orders.
- The **only difference between rounds** is the `present`-step prompt in
  `debate_harness/orchestrator.py` (compressed in R1; complete/structured in R2,
  shipped in PR #13).

## Files

- `produce.py` — generates the single/same/cross answers for one prompt index.
- `judge.py` — runs the blind pairwise judging (both orders) and tallies.
- `round2-answers-p{0,1,2}.json` — the actual Round 2 answers judged (single/same/cross).
- `round2-judge-output.txt` — the Round 2 judge verdicts + reasons + tally.
- `round1-judge-output.txt` — the Round 1 judge verdicts + reasons + tally.

> Note: Round 1's raw *answers* were overwritten when Round 2 reused the output dir;
> the Round 1 judge output (verdicts + the judge's stated reasons, which quote the
> answers) is retained here. Round 2 answers are included in full.

## Reproduce

```bash
pip install -r ../../../requirements.txt
# keys in .env at repo root (ANTHROPIC/OPENAI/OPENROUTER)
export PYTHONPATH="$(pwd)/../../.."      # repo root on sys.path

# produce answers for each prompt (writes JSON; see the path note below)
py -3.13 produce.py 0 && py -3.13 produce.py 1 && py -3.13 produce.py 2

# blind judge + tally
py -3.13 judge.py
```

**Path note:** the scripts write/read `"/tmp/goalres/..."`. Run under Windows
`py`, that string resolves to `F:\tmp\goalres\` (drive-relative), *not* the
Git-Bash `/tmp`. The committed `round2-answers-*.json` are copies of those outputs.
