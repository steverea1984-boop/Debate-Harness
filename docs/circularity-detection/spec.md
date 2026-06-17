# Spec: Circularity detection

## What

Add a cheap, **LLM-free structural** circularity detector that watches for the
spec §10 failure mode — "the last two exchanges restate the previous two" — by
measuring lexical similarity between recent same-speaker turns. It runs every turn
in **observe-only** mode (logged, never acts) by default, mirroring the judge.
A separate, **off-by-default** gate (`enable_circularity_stop`) lets it act as a
**backstop**: when the debate is structurally going in circles, stop early with
`stop_reason="circular"` and present the best synthesis flagged as
non-convergence (the existing `present()` path already handles this). Default
behavior is unchanged: with the gate off, only the turn cap stops the debate.

## Context

- Today the only non-consensus backstop is the hard turn cap
  (`orchestrator.run_debate`, loop bound `range(1, cfg.turn_cap + 1)`).
- The LLM judge already emits a **semantic** `consensus_shape == "circular"` every
  turn (`judge.py`), logged observe-only; it only ends the debate when
  `cfg.enable_judge_stop` is set (`"circular"` is in `judge.TERMINAL_SHAPES`).
  This feature adds a **complementary, structural** signal that needs no model
  call — cheap to run every turn and trivially offline-testable.
- `present()` (`orchestrator.py`) already accepts an arbitrary `stop_reason` and
  instructs the orchestrator: "If they did not converge (circularity or turn cap),
  present the best available synthesis and flag the non-convergence"; its schema
  `outcome_type` includes `circular_no_convergence`. So **no change to `present()`
  is needed** — passing `stop_reason="circular"` is enough.
- Turn structure: the seed is `turns[0]`; debate turns alternate speakers, so a
  turn and the one two back (`turns[-1]` vs `turns[-3]`) are the **same speaker**.
  This is exactly the pairing §10 describes.
- Pattern to mirror: `debate_harness/stages.py` `StageController` — a small,
  config-driven, LLM-free component unit-tested with synthetic input
  (`tests/test_stage_controller.py`).

## Requirements

1. A config gate `enable_circularity_stop` (default `False`). When `False`,
   behavior is identical to today: the detector still computes and logs each turn
   (observe-only) but never stops the debate; only the turn cap stops it.
2. A structural detector that, after each debate turn, compares the two most
   recent same-speaker turn pairs — `(turns[-1], turns[-3])` and
   `(turns[-2], turns[-4])` — and reports a similarity score for each plus an
   `is_circular` verdict.
3. `is_circular` is true only when **both** pair scores are ≥
   `circularity_threshold` **and** at least `circularity_min_turns` debate turns
   have occurred (so it can't fire prematurely or off the seed).
4. Similarity is **case- and whitespace-insensitive** and uses **only the Python
   standard library** (no new dependency, no network).
5. Every turn logs a `circularity_read` event (both scores, `is_circular`,
   whether it was evaluated) — observe-only data for §13 transcript study.
6. When `enable_circularity_stop` is `True` and `is_circular`, the loop stops with
   `stop_reason="circular"` and `present()` produces a
   `circular_no_convergence` result. Precedence: the existing judge-stop check
   (if enabled) is evaluated first, then circularity.
7. The detector is offline-unit-testable with synthetic transcripts (no keys),
   and the existing offline loop test still passes unchanged.
8. Optional CLI flag to enable the backstop for live runs.

## Design

### New component: `debate_harness/circularity.py` → `CircularityDetector`

Kept in its own module (not `stages.py`) because it's a distinct concern; it
matches the `StageController` style (small, config-driven, LLM-free, pure-ish).

```
@dataclass
class CircularityRead:
    evaluated: bool                 # were there enough turns to judge?
    pair_scores: list[float]        # [sim(-1,-3), sim(-2,-4)] when evaluated
    is_circular: bool
    threshold: float

class CircularityDetector:
    def __init__(self, config): ...
    def read(self, transcript) -> CircularityRead   # call after each turn is added
```

`read()`:
- `turns = transcript.turns`; `debate_turn = turns[-1].index`.
- If `len(turns) < 4` or `debate_turn < cfg.circularity_min_turns` →
  `CircularityRead(evaluated=False, pair_scores=[], is_circular=False, ...)`.
- Else compute `s1 = _similar(turns[-1].text, turns[-3].text)` and
  `s2 = _similar(turns[-2].text, turns[-4].text)`;
  `is_circular = s1 >= threshold and s2 >= threshold`.

`_similar(a, b)`: normalize each to a lowercased word-token list
(`re.findall(r"\w+", text.lower())`), then
`difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()`. Stdlib only;
`autojunk=False` avoids difflib's long-sequence heuristic skewing the ratio.
Two empty token lists → similarity `0.0` (degenerate, never circular).

### `run_debate` integration (`orchestrator.py`)

After the turn is added and the stage/judge logging block, before/after the
judge-stop check:

```
detector = CircularityDetector(cfg)            # constructed once, before the loop
...
cread = detector.read(transcript)
self.log.event("circularity_read", after_turn=debate_turn,
               evaluated=cread.evaluated, scores=cread.pair_scores,
               is_circular=cread.is_circular)
if cread.evaluated:
    self.log.md(f"> **Circularity (observe-only):** scores={[round(s,2) for s in cread.pair_scores]} "
                f"| circular={cread.is_circular}\n")

# existing judge-stop check (unchanged) ...
if cfg.enable_circularity_stop and cread.is_circular:
    stop_reason = "circular"
    break
```

No change to `present()` — it already maps a `circular` stop to
`circular_no_convergence` and flags non-convergence.

### Config additions (`config.py`)

```
enable_circularity_stop: bool = False  # gate; default keeps turn-cap-only stopping
circularity_threshold: float = 0.6     # min same-speaker similarity to count as restatement
circularity_min_turns: int = 4         # min debate turns before the detector can fire
```

Serialized automatically by `to_dict()` (`asdict`).

### CLI (`cli.py`)

Add `--circularity-stop` (sets `enable_circularity_stop = True`). Keep the two
numeric knobs config-only.

## Decisions

- **Structural (lexical) detector, separate from the LLM judge.** *Chosen:* a
  stdlib similarity check. *Alternative:* rely only on the judge's semantic
  `circular` read. *Why:* it's free, deterministic, offline-testable, and a
  genuinely independent signal — §10 literally defines circularity as
  *restatement*, which lexical similarity measures directly; the judge's semantic
  read remains available and complementary. *Reversible:* yes.
- **`difflib.SequenceMatcher` on word tokens.** *Chosen:* stdlib, zero deps,
  good enough for "is this turn a restatement of that one." *Alternative:* token
  Jaccard, or an embedding model. *Why not embeddings:* needs a model/keys and
  defeats the offline goal. *Reversible:* yes — `_similar` is one function.
- **Own gate `enable_circularity_stop`, default off.** *Chosen:* separate from
  `enable_judge_stop` so a user can opt into the cheap structural backstop without
  enabling full judge-driven consensus stopping (or vice-versa). *Why:* they're
  different risk profiles; §13 wants observe-only by default. *Reversible:* yes.
- **Compare same-speaker pairs `(-1,-3)` and `(-2,-4)`.** *Chosen:* matches §10's
  "last two exchanges restate the previous two" given strict alternation.
  *Reversible:* yes.
- **New module `circularity.py` vs adding to `stages.py`.** *Chosen:* its own
  module — circularity is not stage logic; keeping modules focused matches the
  repo's structure. *Reversible:* yes.
- `Assumption:` default knobs (`threshold=0.6`, `min_turns=4`) are starting
  points to tune against real transcripts; they only affect logging until the gate
  is on. `0.6` is a deliberately conservative bar for "restatement" on word-token
  `SequenceMatcher.ratio` — flagged for tuning.
- `Assumption:` debate turns strictly alternate speakers (true in
  `run_debate`); the same-speaker pairing depends on it.

## Invariants

- **Default behavior unchanged:** with `enable_circularity_stop=False`, the loop
  stops only at the turn cap (or judge-stop if separately enabled). *Check:* the
  existing `tests/test_offline_loop.py::test_full_loop_invariants` (unique stub
  text, gate off) still asserts `stop_reason == "turn_cap"`.
- **Never fires before `circularity_min_turns`:** *Check:* unit test with a short
  transcript asserts `evaluated is False`.
- **Symmetry / determinism:** `_similar(a, b) == _similar(b, a)`, and identical
  text → `1.0`. *Check:* unit tests.
- **Turn cap still bounds the loop** in all modes.

## Error Behavior

- Empty or whitespace-only turn text → token list empty → similarity `0.0`
  (never circular), no exception.
- Fewer than 4 turns → `evaluated=False`, no comparison attempted.

## Testing Strategy

- **New `tests/test_circularity.py`** (stdlib `unittest`, offline): build
  `Transcript` objects with synthetic alternating turns and assert:
  - not evaluated before `circularity_min_turns`;
  - `is_circular` true when the last two same-speaker pairs are near-identical;
  - false when recent turns are distinct;
  - threshold boundary (just-below vs just-above);
  - case/whitespace-insensitivity; identical text → score `1.0`; empty text → `0.0`.
- **Extend `tests/test_offline_loop.py`**: add a `RepeatingStubProvider` whose
  `complete` returns constant text, run with `enable_circularity_stop=True`, and
  assert the debate stops early with `stop_reason == "circular"` (fewer than
  `1 + turn_cap` turns) and that a `circularity_read` event with
  `is_circular=True` was logged. The existing default-mode test stays as the
  unchanged-behavior guard.
- CI (`.github/workflows/ci.yml`) runs all of it with no keys → stays green.

## Out of Scope

- Changing or replacing the LLM judge's semantic `circular` read (kept as-is).
- Semantic/embedding-based similarity (needs a model).
- Acting on circularity by default (gate stays off until transcripts justify it).
- Circularity-aware *presentation* wording beyond the existing
  `circular_no_convergence` path.
- Detecting circularity across non-adjacent or cross-speaker turns.
