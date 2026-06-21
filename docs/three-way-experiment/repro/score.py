from debate_harness import config as _e  # loads .env
from debate_harness.providers import make_provider
import json, glob, os
from collections import defaultdict

JUDGE = make_provider("openrouter", "anthropic/claude-sonnet-4.6")
SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "properties": {"index": {"type": "integer"},
                       "covered": {"type": "string", "enum": ["yes", "partial", "no"]},
                       "correct": {"type": "boolean"}},
        "required": ["index", "covered", "correct"]}}}, "required": ["items"]}
SYS = ("You are a strict, fair grader. Given a question, a rubric of key points a complete and "
       "correct answer should cover, and a candidate answer, grade EACH rubric point independently: "
       "covered = yes (clearly and substantively addressed), partial (mentioned but thin/vague), or "
       "no (absent). correct = false if the answer states something factually wrong about that point, "
       "else true. Judge substance only, not length or writing style.")

def score(prompt, rubric, answer):
    rub = "\n".join(f"{i}. {r}" for i, r in enumerate(rubric))
    user = f"QUESTION:\n{prompt}\n\nRUBRIC:\n{rub}\n\nANSWER:\n{answer[:9000]}\n\nGrade each rubric point."
    data = JUDGE.complete_json(SYS, user, SCHEMA, 1500)
    items = data["items"]
    cov = sum(1.0 if it["covered"] == "yes" else 0.5 if it["covered"] == "partial" else 0 for it in items)
    errs = sum(1 for it in items if not it.get("correct", True))
    return cov, len(rubric), errs

results = defaultdict(list)
for f in sorted(glob.glob("/tmp/exp3/q*.json")):
    d = json.load(open(f, encoding="utf-8"))
    print("=" * 72); print(os.path.basename(f), "-", d["prompt"][:55])
    for cond in ["single", "debate", "build"]:
        ans = d["answers"][cond]
        cov, n, errs = score(d["prompt"], d["rubric"], ans)
        results[cond].append((cov / n, errs, len(ans)))
        flag = "  <-- possible off-topic" if cov / n < 0.15 else ""
        print(f"  {cond:7} coverage={cov:.1f}/{n} ({cov/n*100:.0f}%)  errors={errs}  len={len(ans)}{flag}")
print("\n=== AVERAGES across all questions ===")
for cond in ["single", "debate", "build"]:
    fr = [r[0] for r in results[cond]]; er = [r[1] for r in results[cond]]; ln = [r[2] for r in results[cond]]
    print(f"  {cond:7} coverage={sum(fr)/len(fr)*100:.0f}%   errors/ans={sum(er)/len(er):.2f}   len={sum(ln)//len(ln)}")
