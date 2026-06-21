import sys, os, json
from debate_harness.config import Config, SlotConfig
from debate_harness import orchestrator
from debate_harness.logging_utils import RunLogger
from debate_harness.providers import make_provider

# Knowledge-rich questions with fixed rubrics (key points a complete, correct
# answer should cover). Rubrics fixed BEFORE scoring.
QUESTIONS = [
    {"prompt": "What are the main tradeoffs between SQL (relational) and NoSQL databases, and when should you choose each?",
     "rubric": ["ACID transactions / strong consistency as a relational strength",
                "rigid predefined schema vs flexible/schema-less data",
                "vertical scaling vs horizontal scale-out",
                "complex queries and JOINs (relational strength)",
                "eventual consistency / CAP-theorem tradeoffs in many NoSQL systems",
                "NoSQL data-model variety (document, key-value, wide-column, graph)",
                "when to choose SQL (structured data, transactions, complex/ad-hoc queries)",
                "when to choose NoSQL (massive scale, evolving schema, known simple access patterns)"]},
    {"prompt": "What were the primary causes of the 2008 global financial crisis?",
     "rubric": ["US housing bubble / inflated home prices",
                "subprime lending and lax underwriting standards",
                "securitization: mortgage-backed securities (MBS) and CDOs",
                "credit-rating-agency failures (AAA ratings on risky tranches)",
                "excessive leverage at banks / investment banks",
                "credit default swaps / unregulated derivatives / AIG",
                "regulatory gaps and the shadow banking system",
                "trigger: falling house prices -> mass defaults -> cascade / Lehman collapse"]},
    {"prompt": "What are the main security risks of applications built on large language models, and how do you mitigate them?",
     "rubric": ["prompt injection (incl. indirect via retrieved content)",
                "jailbreaks / bypassing safety guardrails",
                "sensitive-data leakage / PII / training-data exposure",
                "hallucination / confidently wrong output",
                "insecure output handling (downstream XSS / SQL / code execution)",
                "excessive agency / unsafe tool or action use",
                "supply-chain / model or data poisoning",
                "mitigations: input-output filtering, least privilege, human-in-the-loop, sandboxing"]},
    {"prompt": "What are the key tradeoffs between monolithic and microservices architectures for a software system?",
     "rubric": ["deployment simplicity (monolith) vs independent deployability (microservices)",
                "scaling the whole app vs scaling services independently",
                "team autonomy / Conway's law / org scaling",
                "operational overhead: networking, service discovery, observability",
                "data consistency / distributed transactions difficulty in microservices",
                "development velocity: simpler early (monolith) vs coordination cost",
                "fault isolation vs added network-failure surface and latency",
                "when to choose each (early-stage/small team -> monolith; large/independent scaling -> microservices)"]},
]
REF = ("openrouter", "openai/gpt-4.1-mini")
DS = "openrouter:deepseek/deepseek-chat-v3-0324"
LL = "openrouter:meta-llama/llama-3.3-70b-instruct"
def ep(s): p,_,m=s.partition(":"); return p,m

idx = int(sys.argv[1]); q = QUESTIONS[idx]; prompt = q["prompt"]
ans = {}
# single (comprehensive prompt, no debate)
sp = make_provider(*ep(DS))
ans["single"] = sp.complete(
    "You are a careful expert. Give the best, most complete and correct answer to the "
    "question: cover all the important points, be accurate, and organize it clearly.",
    [{"role": "user", "content": prompt}], 2500)
def run_mode(mode):
    cfg = Config(); cfg.clarify = False; cfg.mode = mode
    cfg.stage1_turns, cfg.stage2_turns, cfg.stage3_turns = 2, 2, 1
    cfg.slot_a = SlotConfig(*ep(DS), "proposer"); cfg.slot_b = SlotConfig(*ep(LL), "skeptic")
    cfg.orchestrator_provider, cfg.orchestrator_model = REF
    lg = RunLogger(label=f"exp3-{mode}-q{idx}")
    return orchestrator.Orchestrator(cfg, lg).run(prompt, ask_user=None).final_answer
ans["debate"] = run_mode("debate")
ans["build"] = run_mode("build")
os.makedirs("/tmp/exp3", exist_ok=True)
json.dump({"prompt": prompt, "rubric": q["rubric"], "answers": ans},
          open(f"/tmp/exp3/q{idx}.json", "w", encoding="utf-8"))
print(f"DONE q{idx}: single={len(ans['single'])} debate={len(ans['debate'])} build={len(ans['build'])}")
