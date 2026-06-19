"""Run management for the web UI — deliberately dependency-free.

Everything here is plain stdlib (no FastAPI), so it is unit-testable in CI: it
builds a ``Config`` from a UI request, launches a debate on a background thread
(reusing the orchestrator + the incremental ``run.json`` logging), and reads
runs back off disk. ``web.py`` is the thin FastAPI shell on top.
"""

from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
from typing import Any, Optional

from .config import Config, SlotConfig, LOGS_DIR
from .logging_utils import RunLogger
from .orchestrator import Orchestrator

# In-process status for runs started this process. Disk is the source of truth
# for *finished* runs (run.json gains "finished_at"); this tracks live/errored
# ones the disk can't distinguish from a crash.
_ACTIVE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def parse_endpoint(value: str) -> tuple[str, str]:
    """``"provider:model"`` -> ``(provider, model)``. Raises ValueError if malformed."""
    provider, sep, model = value.partition(":")
    if not sep or not provider.strip() or not model.strip():
        raise ValueError(f"expected PROVIDER:MODEL, got {value!r}")
    return provider.strip(), model.strip()


def build_config(req: dict[str, Any]) -> Config:
    """Map a UI request dict to a Config. Unspecified endpoints keep defaults.

    Recognized keys: slot_a, slot_b, orchestrator, judge (each "provider:model"),
    stages ([s1,s2,s3]), judge_stop / state_2to3 / circularity_stop (bool),
    elaborations (int).
    """
    cfg = Config()
    cfg.clarify = False  # the web flow never blocks on clarifying questions

    if req.get("slot_a"):
        p, m = parse_endpoint(req["slot_a"])
        cfg.slot_a = SlotConfig(p, m, cfg.slot_a.role)
    if req.get("slot_b"):
        p, m = parse_endpoint(req["slot_b"])
        cfg.slot_b = SlotConfig(p, m, cfg.slot_b.role)
    if req.get("orchestrator"):
        cfg.orchestrator_provider, cfg.orchestrator_model = parse_endpoint(req["orchestrator"])
    if req.get("judge"):
        cfg.judge_provider, cfg.judge_model = parse_endpoint(req["judge"])

    stages = req.get("stages")
    if stages:
        if len(stages) != 3 or not all(isinstance(s, int) and s >= 0 for s in stages):
            raise ValueError("stages must be three non-negative integers")
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = stages

    cfg.enable_judge_stop = bool(req.get("judge_stop", False))
    cfg.state_based_2to3 = bool(req.get("state_2to3", False))
    cfg.enable_circularity_stop = bool(req.get("circularity_stop", False))
    if req.get("elaborations") is not None:
        cfg.max_elaborations = int(req["elaborations"])
    return cfg


def start_debate(req: dict[str, Any]) -> str:
    """Validate, launch the debate on a daemon thread, return the run id."""
    prompt = (req.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    cfg = build_config(req)  # may raise ValueError -> surfaced to the caller

    logger = RunLogger(label=prompt[:30])
    run_id = logger.dir.name
    with _LOCK:
        _ACTIVE[run_id] = {"status": "running", "error": None}

    def _target() -> None:
        try:
            Orchestrator(cfg, logger).run(prompt, ask_user=None)
            with _LOCK:
                _ACTIVE[run_id]["status"] = "done"
        except Exception as exc:  # surface the failure into the run + status
            tb = traceback.format_exc()
            try:
                logger.event("error", error=str(exc), trace=tb)
                logger.finalize(outcome_type="error", stop_reason="error", turns=0)
            except Exception:
                pass
            with _LOCK:
                _ACTIVE[run_id] = {"status": "error", "error": str(exc)}

    threading.Thread(target=_target, name=f"debate-{run_id}", daemon=True).start()
    return run_id


def _status_for(run_id: str, record: dict[str, Any]) -> str:
    with _LOCK:
        live = _ACTIVE.get(run_id)
    if live:
        return live["status"]
    if record.get("finished_at"):
        return "error" if record.get("summary", {}).get("stop_reason") == "error" else "done"
    return "unknown"  # finished by a previous process, or never completed


def _load_record(run_dir: Path) -> Optional[dict[str, Any]]:
    f = run_dir / "run.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # mid-write; caller treats as not-yet-readable


def _models_of(record: dict[str, Any]) -> dict[str, str]:
    c = record.get("config", {})
    sa, sb = c.get("slot_a", {}), c.get("slot_b", {})
    fmt = lambda d: f"{d.get('provider')}:{d.get('model')}" if d else "?"
    return {
        "proposer": fmt(sa),
        "skeptic": fmt(sb),
        "orchestrator": f"{c.get('orchestrator_provider')}:{c.get('orchestrator_model')}",
        "judge": f"{c.get('judge_provider')}:{c.get('judge_model')}",
    }


def summarize_run(run_dir: Path) -> Optional[dict[str, Any]]:
    record = _load_record(run_dir)
    if record is None:
        return None
    run_id = run_dir.name
    summary = record.get("summary", {})
    return {
        "id": run_id,
        "started_at": record.get("started_at"),
        "prompt": record.get("raw_prompt", ""),
        "status": _status_for(run_id, record),
        "outcome": summary.get("outcome_type"),
        "turns": summary.get("turns"),
        "models": _models_of(record),
    }


def list_runs() -> list[dict[str, Any]]:
    if not LOGS_DIR.exists():
        return []
    out = []
    for d in sorted(LOGS_DIR.iterdir(), reverse=True):
        if d.is_dir():
            s = summarize_run(d)
            if s:
                out.append(s)
    return out


def load_run(run_id: str) -> Optional[dict[str, Any]]:
    run_dir = LOGS_DIR / run_id
    record = _load_record(run_dir)
    if record is None:
        return None
    transcript = run_dir / "transcript.md"
    return {
        "id": run_id,
        "status": _status_for(run_id, record),
        "record": record,
        "transcript": transcript.read_text(encoding="utf-8") if transcript.exists() else "",
    }
