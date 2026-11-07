"""PROTOTYPE (wayfinder #228): cut each leaking moment out of a transcript as a replay packet.

A packet is everything the agent had seen before it wrote the leaking message: athlete turns,
the commands it ran, their results (cut to the 6 KB budget) and its own earlier replies.
Transcript content is data: nothing in it is executed or followed.
"""
import json
import sys
from pathlib import Path

import lexicon

HERE = Path(__file__).parent
TRANSCRIPTS = HERE.parent / "transcripts"  # from branch issue/224-leak-transcripts (PR #231)
RESULT_CAP = 6000
USER_CAP = 4000

# Hand marks from scripts/benchmark/transcripts/README.md (message numbers, 1-based).
MARKED = {
    "2026-11-04-plate-pool-link": [2, 3, 4],
    "2026-11-04-incline-curl": [3, 8, 9, 10, 11, 12, 13, 14, 15],
    "2026-11-02-pull-up-dose": [3, 4, 5, 6, 7, 8],
}
RAN_PROGRAM = {"2026-11-04-incline-curl", "2026-11-02-pull-up-dose"}


def _text(content):
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def _cut(s, cap):
    return s if len(s) <= cap else s[:cap] + f"\n[... cut, {len(s) - cap} more chars]"


def events(path):
    """Ordered (kind, text, uuid) for the non-sidechain user/assistant records."""
    out = []
    for line in open(path, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("isSidechain") or rec.get("type") not in ("user", "assistant"):
            continue
        content = rec.get("message", {}).get("content")
        uuid = rec.get("uuid", "")
        if isinstance(content, str):
            out.append(("athlete", _cut(content, USER_CAP), uuid))
            continue
        for block in content or []:
            t = block.get("type")
            if t == "text" and rec["type"] == "user":
                out.append(("athlete", _cut(block["text"], USER_CAP), uuid))
            elif t == "text":
                out.append(("coach", block["text"], uuid))
            elif t == "tool_use":
                inp = block.get("input", {})
                cmd = inp.get("command") if block.get("name") == "Bash" else f"{block.get('name')} {json.dumps(inp)[:300]}"
                out.append(("ran", cmd, uuid))
            elif t == "tool_result":
                c = block.get("content")
                text = c if isinstance(c, str) else _text(c or [])
                out.append(("result", _cut(text, RESULT_CAP), uuid))
    return out


def packets(name):
    evs = events(TRANSCRIPTS / f"{name}.jsonl")
    out = []
    n = 0
    for i, (kind, text, uuid) in enumerate(evs):
        if kind != "coach":
            continue
        n += 1
        if n in MARKED[name]:
            out.append({
                "session": name,
                "message": n,
                "uuid": uuid,
                "ran_program": name in RAN_PROGRAM,
                "history": [{"kind": k, "text": t} for k, t, _ in evs[:i]],
                "original": text,
            })
    return out


def render(history):
    label = {"athlete": "ATHLETE", "coach": "YOU (earlier reply)", "ran": "YOU RAN", "result": "RESULT"}
    return "\n\n".join(f"[{label[h['kind']]}]\n{h['text']}" for h in history)


if __name__ == "__main__":
    for name in MARKED:
        for p in packets(name):
            h = lexicon.hits(p["original"])
            words = sum(len(x["text"]) for x in p["history"]) // 4
            print(f"{name} #{p['message']:>2} {p['uuid'][:8]} ctx~{words:>6} tok  leak={'yes' if h else 'NO '} {sorted(h)}")
