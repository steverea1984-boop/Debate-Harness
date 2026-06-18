"""Command-line entry point for the debate harness.

Examples
--------
Single prompt (interactive — may ask clarifying questions):
    python -m debate_harness.cli "Should a startup default to a monolith or microservices?"

Read the prompt from stdin:
    echo "..." | python -m debate_harness.cli -

Batch over a file of prompts (one per line; never asks clarifying questions):
    python -m debate_harness.cli --batch prompts/sample_prompts.txt

Useful flags:
    --no-clarify           skip clarifying questions even in interactive mode
    --turn-cap-stages a b c  override stage1/stage2/stage3 turn counts
    --judge-stop           let a confident judge read end the debate early
    --state-2to3           let the judge's read drive the stage 2->3 transition
    --same-model           run both slots on the Anthropic model (sycophancy baseline)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, SlotConfig
from .logging_utils import RunLogger
from .orchestrator import Orchestrator


def _ask_user(questions: list[str]) -> dict[str, str]:
    print("\nThe orchestrator has clarifying questions before refining your prompt:")
    answers: dict[str, str] = {}
    for q in questions:
        try:
            ans = input(f"  • {q}\n    > ").strip()
        except EOFError:
            ans = ""
        answers[q] = ans
    print()
    return answers


def _build_config(args: argparse.Namespace) -> Config:
    cfg = Config()
    if args.no_clarify:
        cfg.clarify = False
    if args.judge_stop:
        cfg.enable_judge_stop = True
    if args.state_2to3:
        cfg.state_based_2to3 = True
    if args.elaborations is not None:
        cfg.max_elaborations = args.elaborations
    if args.stages is not None:
        cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = args.stages
    if args.same_model:
        # Sycophancy baseline (spec §9): both slots on the Anthropic model,
        # complementary roles preserved so it's still proposer vs skeptic.
        cfg.slot_b = SlotConfig(
            provider="anthropic", model=cfg.slot_a.model, role=cfg.slot_b.role
        )
    return cfg


def _print_result(result) -> None:
    print("\n" + "=" * 70)
    print(f"OUTCOME: {result.outcome_type}   (stop reason: {result.stop_reason})")
    print("=" * 70)
    print("\nFINAL ANSWER:\n")
    print(result.final_answer)
    if result.residual_disagreement.strip():
        print("\nRESIDUAL DISAGREEMENT:\n")
        print(result.residual_disagreement)
    if result.note_to_user.strip():
        print(f"\nNOTE: {result.note_to_user}")
    print(f"\nFull log: {result.log_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="debate_harness",
        description="Run a staged, sequential debate between two models.",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="The prompt to debate. Use '-' to read from stdin. Omit when using --batch.",
    )
    parser.add_argument("--batch", metavar="FILE", help="Run every prompt in FILE.")
    parser.add_argument("--no-clarify", action="store_true", help="Never ask clarifying questions.")
    parser.add_argument("--judge-stop", action="store_true", help="Let the judge end the debate early.")
    parser.add_argument("--state-2to3", action="store_true", help="Let the judge's read drive the stage 2->3 transition (default: pure timer).")
    parser.add_argument("--same-model", action="store_true", help="Run both slots on the Anthropic model (baseline).")
    parser.add_argument("--elaborations", type=int, default=None, help="Max orchestrator elaboration requests (default 0).")
    parser.add_argument(
        "--stages",
        type=int,
        nargs=3,
        metavar=("S1", "S2", "S3"),
        default=None,
        help="Turn counts for stage 1/2/3 (default 3 3 2).",
    )
    args = parser.parse_args(argv)

    cfg = _build_config(args)

    if args.batch:
        path = Path(args.batch)
        if not path.exists():
            parser.error(f"Batch file not found: {path}")
        prompts = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not prompts:
            parser.error("Batch file has no prompts.")
        # Batch can't take clarifying input.
        cfg.clarify = False
        print(f"Running {len(prompts)} prompt(s) in batch mode...\n")
        for i, raw in enumerate(prompts, 1):
            print(f"\n[{i}/{len(prompts)}] {raw}")
            orch = Orchestrator(cfg, RunLogger(label=raw[:30]))
            try:
                result = orch.run(raw, ask_user=None)
                _print_result(result)
            except Exception as exc:  # keep the batch going
                print(f"  !! Failed: {exc}")
        return 0

    # Single prompt.
    if args.prompt == "-" or (args.prompt is None and not sys.stdin.isatty()):
        raw = sys.stdin.read().strip()
    elif args.prompt:
        raw = args.prompt
    else:
        parser.error("Provide a prompt, use '-' for stdin, or pass --batch FILE.")

    orch = Orchestrator(cfg, RunLogger(label=raw[:30]))
    result = orch.run(raw, ask_user=None if cfg.clarify is False else _ask_user)
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
