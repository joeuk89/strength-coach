"""PROTOTYPE (wayfinder #228): the comparison table from results/."""
import json
import statistics
from collections import Counter
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
ORDER = ["base", "rule", "rule_skill", "hook", "split"]
LABEL = {
    "base": "today's CLAUDE.md (no rule)",
    "rule": "voice section in CLAUDE.md",
    "rule_skill": "voice section + skill closing line",
    "hook": "rule_skill + Stop-hook rewrite on a hit",
    "split": "rule_skill + runner subagent brief",
}


def final(rec):
    if rec["mechanism"] == "hook":
        return rec.get("second_hits", rec["first_hits"])
    return rec["first_hits"]


def main():
    rows = []
    per_message = {}
    for m in ORDER:
        d = RESULTS / m
        if not d.exists():
            continue
        recs = [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]
        if not recs:
            continue
        leaking = sum(1 for r in recs if final(r))
        classes = Counter(c for r in recs for c in final(r))
        secs = [r["first"]["seconds"] + r.get("second", {}).get("seconds", 0) + r.get("runner", {}).get("seconds", 0) for r in recs]
        cost = [(r["first"].get("cost_usd") or 0) + (r.get("second", {}).get("cost_usd") or 0) + (r.get("runner", {}).get("cost_usd") or 0) for r in recs]
        calls = statistics.mean(1 + ("second" in r) + ("runner" in r) for r in recs)
        rows.append((m, len(recs), leaking, dict(classes), statistics.median(secs), sum(cost), recs[0]["system_tokens"], calls))
        for r in recs:
            per_message.setdefault((r["session"], r["message"]), {})[m] = final(r)

    print("| Mechanism | Leaking / messages | Hit classes | Median seconds | Calls per reply | Instruction tokens | Cost of 18 (USD) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for m, n, leaking, classes, med, cost, systok, calls in rows:
        cls = ", ".join(f"{k} {v}" for k, v in sorted(classes.items(), key=lambda kv: -kv[1])) or "none"
        print(f"| {LABEL[m]} | {leaking}/{n} | {cls} | {med:.0f} | {calls:.1f} | {systok} | {cost:.2f} |")

    print("\nPer message (terms that leaked):\n")
    print("| Session | # | " + " | ".join(m for m in ORDER if any(m in v for v in per_message.values())) + " |")
    print("| --- | --- | " + " | ".join("---" for m in ORDER if any(m in v for v in per_message.values())) + " |")
    for (s, n), by in sorted(per_message.items()):
        cells = []
        for m in ORDER:
            if not any(m in v for v in per_message.values()):
                continue
            h = by.get(m)
            if h is None:
                cells.append("-")
            elif not h:
                cells.append("clean")
            else:
                terms = sorted({t for ts in h.values() for t in ts})
                cells.append("; ".join(terms)[:80].replace("|", "\\|"))
        print(f"| {s[11:]} | {n} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
