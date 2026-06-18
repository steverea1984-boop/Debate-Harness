"""Regression tests for cross-platform (utf-8) file I/O.

Guards the bug class where the package read/wrote files with the platform-default
encoding instead of utf-8. On Windows that default is cp1252, which breaks two
ways:

  - **Writes crash.** ``transcript.md`` could not encode the ``->`` arrow
    (U+2192) the orchestrator uses in stage labels, so every run raised
    ``UnicodeEncodeError`` before a transcript was written.
  - **Reads silently corrupt.** The role/orchestrator prompt files contain
    em-dashes; reading them as cp1252 yields mojibake (no exception), feeding
    corrupted system prompts to the models.

CI on Linux (utf-8 default) never caught either. These tests force non-ASCII
content through every read/write path and assert it round-trips exactly.

Run locally with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from debate_harness import logging_utils
from debate_harness.logging_utils import RunLogger
from debate_harness.orchestrator import _read

# Characters that are absent from cp1252 — writing these with the platform
# default on Windows raises UnicodeEncodeError.
NON_ASCII = "stage 1 → stage 2 — résumé \U0001f600"


class RunLoggerEncodingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig_logs = logging_utils.LOGS_DIR
        logging_utils.LOGS_DIR = Path(self._tmp.name)
        self.addCleanup(setattr, logging_utils, "LOGS_DIR", self._orig_logs)

    def test_transcript_handles_non_ascii(self):
        logger = RunLogger(label="encoding-test")
        # Would raise UnicodeEncodeError on Windows before the utf-8 fix.
        logger.md(NON_ASCII)
        logger.md_header("Résolution → done", level=2)

        written = (logger.dir / "transcript.md").read_text(encoding="utf-8")
        self.assertIn("→", written)
        self.assertIn("\U0001f600", written)
        self.assertIn("Résolution", written)

    def test_run_json_round_trips_non_ascii(self):
        # Behavioral round-trip, not an encoding-crash guard: json.dumps defaults
        # to ensure_ascii=True, so run.json is ASCII regardless of file encoding.
        # This guards that non-ASCII event/summary data survives the
        # serialize -> write -> read -> deserialize cycle intact.
        logger = RunLogger(label="encoding-test")
        logger.event("turn", text=NON_ASCII)
        path = logger.finalize(note=NON_ASCII)

        data = json.loads((path / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(data["events"][0]["text"], NON_ASCII)
        self.assertEqual(data["summary"]["note"], NON_ASCII)


class ReadEncodingTest(unittest.TestCase):
    """Guards the read side: role/prompt files are utf-8 and must round-trip.

    Without ``encoding="utf-8"`` in ``orchestrator._read``, reading a utf-8 file
    on a cp1252 Windows host returns mojibake (silent corruption), so the models
    would receive a garbled system prompt.
    """

    def test_read_returns_exact_unicode(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "role.md"
            p.write_text(f"  {NON_ASCII}  \n", encoding="utf-8")
            self.assertEqual(_read(p), NON_ASCII)  # exact, stripped, no mojibake


if __name__ == "__main__":
    unittest.main()
