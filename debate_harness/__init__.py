"""Multi-Model Debate Harness — minimal prototype.

Orchestrates a staged, sequential debate between two debater models (one
Anthropic, one OpenAI) refereed by an Anthropic orchestrator, with an
observe-only consensus/stage judge running alongside. See the design spec and
README for the full picture.
"""

__version__ = "0.1.0"
