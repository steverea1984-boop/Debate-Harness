"""Full logging of every run (spec §12: 'Full logging of every turn, every stage
decision, every intervention').

Each run gets its own timestamped directory under ``logs/`` containing:
  - ``run.json``       — structured, machine-readable record of everything.
  - ``transcript.md``  — human-readable narrative for reading after the fact.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LOGS_DIR


class RunLogger:
    def __init__(self, label: str = "run"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
        # Short random suffix so two runs started in the same second with the same
        # label (e.g. the same prompt across models in a comparison sweep) get
        # distinct directories instead of interleaving into one.
        self.dir = LOGS_DIR / f"{ts}-{safe}-{uuid.uuid4().hex[:4]}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.record: dict[str, Any] = {
            "started_at": ts,
            "events": [],
        }
        self._md_lines: list[str] = []

    # --- structured event log ---------------------------------------------
    def event(self, kind: str, **data: Any) -> None:
        self.record["events"].append({"kind": kind, **data})
        self._flush_json()

    def set(self, key: str, value: Any) -> None:
        self.record[key] = value
        self._flush_json()

    # --- human-readable transcript ----------------------------------------
    def md(self, text: str = "") -> None:
        self._md_lines.append(text)
        (self.dir / "transcript.md").write_text(
            "\n".join(self._md_lines), encoding="utf-8"
        )

    def md_header(self, text: str, level: int = 2) -> None:
        self.md(f"\n{'#' * level} {text}\n")

    def _flush_json(self) -> None:
        (self.dir / "run.json").write_text(
            json.dumps(self.record, indent=2), encoding="utf-8"
        )

    def finalize(self, **summary: Any) -> Path:
        self.record["finished_at"] = datetime.now(timezone.utc).strftime(
            "%Y%m%d-%H%M%S"
        )
        self.record["summary"] = summary
        self._flush_json()
        return self.dir
