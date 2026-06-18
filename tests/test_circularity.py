"""Offline unit tests for CircularityDetector (spec §10).

No models, no network: synthetic transcripts of alternating-speaker turns are fed
to the detector and we assert its verdict. Covers the min-turns gate, detection of
same-speaker restatement, distinctness, the threshold boundary, and the
similarity helper's properties.
"""

from __future__ import annotations

import unittest

from debate_harness.circularity import CircularityDetector, _similar
from debate_harness.config import Config
from debate_harness.transcript import Transcript, Turn


def make_transcript(texts: list[str]) -> Transcript:
    """Build a transcript from texts; index 0 is the seed, speakers alternate."""
    t = Transcript(refined_prompt="Q")
    for i, text in enumerate(texts):
        slot = "A" if i % 2 == 0 else "B"
        role = "proposer" if slot == "A" else "skeptic"
        t.add(
            Turn(
                index=i,
                speaker_slot=slot,
                speaker_role=role,
                stage=1,
                text=text,
                kind="seed" if i == 0 else "debate",
            )
        )
    return t


def _cfg(**overrides) -> Config:
    cfg = Config()
    cfg.circularity_min_turns = 4
    cfg.circularity_threshold = 0.6
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


A = "We should choose the monolith because it is simpler to deploy and operate."
B = "The monolith will not scale and the team will regret it within a year."


class SimilarityHelperTest(unittest.TestCase):
    def test_identical_is_one(self):
        self.assertEqual(_similar(A, A), 1.0)

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(_similar(A, "  " + A.upper() + "  \n"), 1.0)

    def test_distinct_is_low(self):
        self.assertLess(_similar(A, B), 0.6)

    def test_symmetry(self):
        self.assertEqual(_similar(A, B), _similar(B, A))

    def test_empty_is_zero(self):
        self.assertEqual(_similar("", ""), 0.0)
        self.assertEqual(_similar(A, ""), 0.0)


class DetectorTest(unittest.TestCase):
    def test_not_evaluated_before_min_turns(self):
        det = CircularityDetector(_cfg())
        # 4 turns -> last index is 3 < min_turns(4): not enough debate turns yet.
        read = det.read(make_transcript([A, B, A, B]))
        self.assertFalse(read.evaluated)
        self.assertFalse(read.is_circular)

    def test_too_few_turns_not_evaluated(self):
        det = CircularityDetector(_cfg())
        read = det.read(make_transcript([A, B, A]))
        self.assertFalse(read.evaluated)

    def test_detects_circular_restatement(self):
        det = CircularityDetector(_cfg())
        # idx: 0 seed, 1=B, 2=A, 3=B(restates 1), 4=A(restates 2) -> both pairs 1.0
        read = det.read(make_transcript(["seed answer", B, A, B, A]))
        self.assertTrue(read.evaluated)
        self.assertTrue(read.is_circular)
        self.assertEqual(read.pair_scores, [1.0, 1.0])

    def test_distinct_recent_turns_not_circular(self):
        det = CircularityDetector(_cfg())
        texts = [
            "seed",
            "point one from the skeptic",
            "point two from the proposer",
            "a totally different skeptic objection about cost",
            "a fresh proposer argument about hiring and onboarding",
        ]
        read = det.read(make_transcript(texts))
        self.assertTrue(read.evaluated)
        self.assertFalse(read.is_circular)

    def test_requires_both_pairs(self):
        det = CircularityDetector(_cfg())
        # Only the A-pair restates; the B-pair is fresh -> not circular.
        read = det.read(make_transcript(["seed", B, A, "a brand new objection", A]))
        self.assertTrue(read.evaluated)
        self.assertFalse(read.is_circular)

    def test_threshold_governs_verdict(self):
        # One word changed -> high but <1.0 similarity; threshold flips the verdict.
        A2 = A.replace("simpler", "easier")
        B2 = B.replace("year", "month")
        texts = ["seed", B, A, B2, A2]
        self.assertTrue(CircularityDetector(_cfg(circularity_threshold=0.5)).read(make_transcript(texts)).is_circular)
        self.assertFalse(CircularityDetector(_cfg(circularity_threshold=0.99)).read(make_transcript(texts)).is_circular)


if __name__ == "__main__":
    unittest.main()
