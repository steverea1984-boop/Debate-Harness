import sys, os, json
from debate_harness.config import Config, SlotConfig
from debate_harness import orchestrator
from debate_harness.logging_utils import RunLogger
from debate_harness.providers import make_provider

PROMPTS = [
    "Is nuclear power a necessary part of decarbonizing the electricity grid, or can renewables plus storage do it alone?",
    "For a 30-year-old with a stable income, is paying off a 4% mortgage early better than investing the difference in an index fund?",
    "Should an early-stage startup default to a monolith or microservices for a new product?",
]
REF = ("openrouter", "openai/gpt-4.1-mini")
DS = "openrouter:deepseek/deepseek-chat-v3-0324"
QW = "openrouter:meta-llama/llama-3.3-70b-instruct"
def ep(s): p,_,m=s.partition(":"); return p,m

idx = int(sys.argv[1]); prompt = PROMPTS[idx]
out = {}
# SINGLE: one model, no debate
sp = make_provider(*ep(DS))
out["single"] = sp.complete(
    "You are a careful expert. Give the best, well-reasoned answer to the question: "
    "take a clear position, support it, and honestly name the key tradeoffs and when you'd decide differently.",
    [{"role": "user", "content": prompt}], 2000)
# Debates
def debate(a, b, label):
    cfg = Config(); cfg.clarify = False
    cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 2, 2, 1
    cfg.slot_a = SlotConfig(*ep(a), "proposer"); cfg.slot_b = SlotConfig(*ep(b), "skeptic")
    cfg.orchestrator_provider, cfg.orchestrator_model = REF
    lg = RunLogger(label=f"goal-{label}-p{idx}")
    return orchestrator.Orchestrator(cfg, lg).run(prompt, ask_user=None).final_answer
out["same"] = debate(DS, DS, "same")
out["cross"] = debate(DS, QW, "cross")
os.makedirs("/tmp/goalres", exist_ok=True)
json.dump({"prompt": prompt, "answers": out}, open(f"/tmp/goalres/p{idx}.json", "w", encoding="utf-8"))
print(f"DONE p{idx}: single={len(out['single'])}c same={len(out['same'])}c cross={len(out['cross'])}c")
