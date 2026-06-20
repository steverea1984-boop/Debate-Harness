from debate_harness import config as _load_env  # noqa: importing config runs load_dotenv()
import json, glob
from collections import Counter
from debate_harness.providers import make_provider

JUDGE = make_provider("openrouter", "anthropic/claude-sonnet-4.6")  # strong, neutral to deepseek/qwen
SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"winner": {"type": "string", "enum": ["1", "2", "tie"]},
                         "reason": {"type": "string"}},
          "required": ["winner", "reason"]}
SYS = ("You are an impartial expert evaluator. Given a question and two candidate answers, "
       "decide which is the better-reasoned answer: more accurate, better-calibrated, more "
       "decision-useful, and more honest about tradeoffs. Ignore length and writing style; "
       "judge substance. If genuinely equal, answer tie.")
def ask(prompt, first, second):
    user = (f"QUESTION:\n{prompt}\n\n=== ANSWER 1 ===\n{first[:12000]}\n\n"
            f"=== ANSWER 2 ===\n{second[:12000]}\n\nWhich answer is better reasoned?")
    return JUDGE.complete_json(SYS, user, SCHEMA, 600)
def compare(prompt, xl, xt, yl, yt):
    r1 = ask(prompt, xt, yt); w1 = xl if r1["winner"]=="1" else yl if r1["winner"]=="2" else "tie"
    r2 = ask(prompt, yt, xt); w2 = yl if r2["winner"]=="1" else xl if r2["winner"]=="2" else "tie"
    return w1, w2, r1["reason"]
tally = Counter()
for f in sorted(glob.glob("/tmp/goalres/p*.json")):
    d = json.load(open(f, encoding="utf-8")); pr = d["prompt"]; a = d["answers"]
    print("=" * 72); print(pr[:60])
    for x, y in [("cross", "single"), ("cross", "same"), ("same", "single")]:
        w1, w2, reason = compare(pr, x, a[x], y, a[y])
        consistent = (w1 == w2)
        verdict = (w1 if w1 != "tie" else "tie") if consistent else f"SPLIT ({w1} then {w2})"
        key = (f"{x}_vs_{y}", w1 if consistent else "split")
        tally[key] += 1
        print(f"  {x:6} vs {y:6}: {verdict}")
        print(f"       why: {reason[:140]}")
print("\n=== TALLY (verdicts consistent across both answer orders) ===")
for k, v in sorted(tally.items()): print(f"  {k[0]:16} -> {k[1]:8} : {v}")
