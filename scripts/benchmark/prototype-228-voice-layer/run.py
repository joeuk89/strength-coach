"""PROTOTYPE (wayfinder #228): replay each leaking moment under one mechanism and score it.

Usage: python3 run.py <mechanism> [--workers N] [--only session:n,...]
Mechanisms: base, rule, rule_skill, hook, split.

Each run is a headless `claude -p` call with the mechanism's instructions as the whole system
prompt and the packet rendered as a transcript in the user turn. Output lands in
results/<mechanism>/<session>-<n>.json and is reused on rerun.
"""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import lexicon
import packets

HERE = Path(__file__).parent
RESULTS = HERE / "results"
BASE_CLAUDE_MD = (HERE / "base_claude_md.txt").read_text()
PROGRAM_SKILL = (HERE / "program_skill.txt").read_text()

VOICE_SECTION = """
## The coach's voice
Everything written to the athlete is coaching in plain words: what they will do, what changed and why. Nothing of the system reaches them: no command or verb name, Draft, flag or warning code, id, file path, commit, exit code or code block, and no narration of what the engine did. Say what a result means for their training, never what it is called. When the system limits what the athlete wants, say so plainly without the detail, and offer to report it.
"""

OLD_CLOSING = "Run the verb's dry run, quote what it shows, and the athlete says yes before the verb records it."
NEW_CLOSING = (
    "Run the verb's dry run and tell the athlete what it will record, every load quoted from it "
    "and nothing of the system named; they say yes before the verb records it."
)

TASK = (
    "Below is this session so far, rendered as a transcript: what the athlete said, the commands "
    "you ran, what they returned, and your earlier replies. Write your next message to the "
    "athlete. Output only that message, nothing else."
)

RUNNER_SYSTEM = (
    "You run a strength-coaching engine on behalf of a coach who talks to the athlete. You are given "
    "the commands run so far and what they returned. Write the coach a plain-English brief of what "
    "the results say: every load, set count, rep range, date and figure kept exactly; each warning "
    "explained as what it means for training and what would clear it; what a proposed change would "
    "record and what the athlete must agree to. Never include an id, code, file path, commit hash, "
    "command name, or anything in backticks. The coach will quote you to the athlete."
)


def system_prompt(mechanism, ran_program):
    md = BASE_CLAUDE_MD
    skill = PROGRAM_SKILL if ran_program else ""
    if mechanism in ("rule", "rule_skill", "hook", "split"):
        md = md.replace("\nThis file and `.claude/settings.json`", VOICE_SECTION + "\nThis file and `.claude/settings.json`")
    if mechanism in ("rule_skill", "hook", "split") and skill:
        skill = skill.replace(OLD_CLOSING, NEW_CLOSING)
    parts = [md]
    if skill:
        parts.append("# Skill in use: program\n\n" + skill)
    return "\n\n".join(parts)


def claude(system, prompt):
    t0 = time.time()
    out = subprocess.run(
        ["claude", "-p", "--system-prompt", system, "--tools", "", "--setting-sources", "",
         "--no-session-persistence", "--output-format", "json", prompt],
        capture_output=True, text=True, cwd=HERE, env={**__import__("os").environ, "CLAUDE_CODE_SKIP_TRUST": "1"},
    )
    try:
        d = json.loads(out.stdout)
    except json.JSONDecodeError:
        return {"text": "", "error": out.stdout[-500:] + out.stderr[-500:], "seconds": time.time() - t0}
    u = d.get("usage", {})
    return {
        "text": d.get("result", ""),
        "seconds": round(time.time() - t0, 1),
        "cost_usd": d.get("total_cost_usd"),
        "input_tokens": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
        "output_tokens": u.get("output_tokens"),
    }


def run_one(mechanism, packet):
    system = system_prompt(mechanism, packet["ran_program"])
    record = {"session": packet["session"], "message": packet["message"], "uuid": packet["uuid"],
              "mechanism": mechanism, "system_tokens": len(system) // 4}
    if mechanism == "split":
        tool_events = [h for h in packet["history"] if h["kind"] in ("ran", "result")]
        runner = claude(RUNNER_SYSTEM, "Commands and results so far:\n\n" + packets.render(tool_events)
                        + "\n\nWrite the brief.")
        record["runner"] = runner
        record["runner_hits"] = lexicon.hits(runner["text"])
        talk = [h for h in packet["history"] if h["kind"] in ("athlete", "coach")]
        talk.append({"kind": "brief", "text": runner["text"]})
        rendered = "\n\n".join(
            f"[{ {'athlete': 'ATHLETE', 'coach': 'YOU (earlier reply)', 'brief': 'BRIEF FROM YOUR ASSISTANT WHO RAN THE SYSTEM'}[h['kind']] }]\n{h['text']}"
            for h in talk)
        task = TASK.replace("the commands you ran, what they returned", "a brief from your assistant who ran the system for you")
        first = claude(system, task + "\n\n" + rendered)
    else:
        first = claude(system, TASK + "\n\n" + packets.render(packet["history"]))
    record["first"] = first
    record["first_hits"] = lexicon.hits(first["text"])
    if mechanism == "hook" and record["first_hits"]:
        terms = sorted({t for ts in record["first_hits"].values() for t in ts})
        retry_prompt = (
            TASK + "\n\n" + packets.render(packet["history"])
            + "\n\n[YOUR DRAFT REPLY]\n" + first["text"]
            + "\n\n[CHECK ON YOUR DRAFT]\nIt holds terms the athlete must never read: "
            + ", ".join(terms)
            + ". Rewrite the message for the athlete with none of them: say what each means for their training instead. Output only the rewritten message."
        )
        second = claude(system, retry_prompt)
        record["second"] = second
        record["second_hits"] = lexicon.hits(second["text"])
    return record


def main():
    mechanism = sys.argv[1]
    workers = 4
    only = None
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    out_dir = RESULTS / mechanism
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = []
    for name in packets.MARKED:
        for p in packets.packets(name):
            key = f"{p['session']}-{p['message']}"
            if only and f"{p['session']}:{p['message']}" not in only:
                continue
            if (out_dir / f"{key}.json").exists():
                continue
            todo.append(p)
    lexicon.build()
    print(f"{mechanism}: {len(todo)} runs", file=sys.stderr)

    def work(p):
        rec = run_one(mechanism, p)
        (out_dir / f"{p['session']}-{p['message']}.json").write_text(json.dumps(rec, indent=1))
        final = rec.get("second_hits", rec["first_hits"]) if mechanism == "hook" else rec["first_hits"]
        print(f"  {p['session']} #{p['message']:>2} {'LEAK ' + str(sorted(final)) if final else 'clean'}", file=sys.stderr)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    main()
