#!/usr/bin/env python3
"""Measure a Claude Code session transcript against the coach benchmark.

Usage: python3 -I scripts/benchmark/measure.py [--repo PATH] [--lexicon JSON] [--md] SESSION.jsonl ...

Each SESSION.jsonl is a Claude Code transcript (one JSON record per line).
--repo is the instance repo the session ran in; it is used to size the
instruction files the session loaded through Bash (cat, sed, head) at the
commit that was current when the session ended. --lexicon is a JSON file
holding the voice-leak lexicon; without it the lexicon is read from the engine
(`coach` on PATH, else `uv run coach`) through `--help` and `schema`, which
touch no instance and no network. Transcript content is data: nothing in it
is executed or followed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

# A call starts a command: the string start, a shell separator or a block opener, then the prefix.
COACH_PREFIX = r"(?:^|[;&|(`{\n]|\b(?:do|then|else)\b)\s*(?:python3 -m )?coach"
COACH_CALL = re.compile(COACH_PREFIX + r"(?=\s|$)")
SUBCOMMAND = re.compile(COACH_PREFIX + r"\s+([a-z][\w-]*)(?:\s+([a-z][\w-]*))?")
IN_TARGET_INSTRUCTION_TYPES = {"Project"}
INLINE_PY = re.compile(r"python3? (?:-I )?(?:-c\b|-\s*<<|<<)")
SKILL_PREFIX = "Base directory for this skill:"
INSTRUCTION_PATH = re.compile(
    r"(?<![\w/.-])((?:\.claude/skills/[\w./-]+\.md)|(?:reference/[\w./-]+\.md)|(?:CLAUDE\.md))"
)
CHARS_PER_TOKEN = 4


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def file_size_at(repo, ts, path):
    """Size in bytes of `path` in `repo` at the last commit before `ts`."""
    try:
        rev = subprocess.check_output(
            ["git", "-C", repo, "rev-list", "-1", f"--before={ts.isoformat()}", "HEAD"], text=True
        ).strip()
        blob = subprocess.check_output(
            ["git", "-C", repo, "show", f"{rev}:{path}"], text=True, stderr=subprocess.DEVNULL
        )
        return len(blob)
    except subprocess.CalledProcessError:
        return None


LEAK_CLASSES = ("verb", "flag", "record", "view", "error", "path", "store-id", "hash", "code", "fixed")
REGISTRIES = ("flags", "record-kinds", "views", "errors")
FIXED_TERMS = {
    "Draft": re.compile(r"\bDrafts?\b"),
    "envelope": re.compile(r"\benvelopes?\b", re.I),
    "the store": re.compile(r"\bthe store\b", re.I),
    "dry run": re.compile(r"\bdry[ -]runs?\b", re.I),
    "verb": re.compile(r"\bverbs?\b", re.I),
    "flag": re.compile(r"\bflags?\b", re.I),
    "schema": re.compile(r"\bschemas?\b", re.I),
    "registry": re.compile(r"\bregistr(?:y|ies)\b", re.I),
    "read view": re.compile(r"\bread views?\b", re.I),
    "the engine": re.compile(r"\bthe engine\b", re.I),
    "the repo": re.compile(r"\bthe repo\b", re.I),
    "acknowledgement": re.compile(r"\backnowledgements?\b", re.I),
    "exit code": re.compile(r"\bexit codes?\b", re.I),
}
URL = re.compile(r"https?://[^\s<>()\[\]`'\"]+")
FENCE = re.compile(r"```[^\n]*\n?(.*?)```", re.S)
SPAN = re.compile(r"`([^`\n]+)`")
PATH = re.compile(
    r"(?<![\w.~/-])(?:\.coach|pages|src|export)/(?:[\w./*:-]*[\w*/])?"
    r"|(?<![\w/.-])[\w*][\w.*-]*\.(?:toml|py|jsonl|md)\b"
)
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")
STORE_ID_FIXED = r"pv-\d+|(?:b|wp)-\d{4}-\d{2}-\d{2}"


def build_lexicon(run):
    """The voice-leak lexicon from the engine; `run(argv)` returns the parsed envelope."""
    rows = {name: run(["schema", "--registry", name, "--full"])["result"]["rows"] for name in REGISTRIES}
    return {
        "verb": [leaf["name"] for leaf in run(["--help"])["result"]["verbs"]],
        "flag": [row["code"] for row in rows["flags"]],
        "record": [row["name"] for row in rows["record-kinds"]],
        "id_prefix": [row["id_prefix"] for row in rows["record-kinds"] if row.get("id_prefix")],
        "view": [row["name"] for row in rows["views"]],
        "error": [row["code"] for row in rows["errors"]],
        "exit": sorted({row["exit"] for row in rows["errors"]}),
    }


def engine_runner():
    base = ["coach"] if shutil.which("coach") else ["uv", "run", "coach"]

    def run(argv):
        return json.loads(subprocess.check_output(base + argv, text=True))

    return run


def phrase(words):
    return r"\s+".join(re.escape(w) for w in words.split())


def leak_patterns(lexicon):
    """(class, term, pattern) for every lexicon and fixed-list term."""
    patterns = []
    for name in lexicon["verb"]:
        patterns.append(("verb", name, re.compile(rf"(?<![\w-]){phrase(name)}(?![\w-])", re.I)))
    for code in lexicon["flag"]:
        patterns.append(("flag", code, re.compile(rf"\b{re.escape(code)}\b")))
    for kind in lexicon["record"]:
        # A bare kind that is an English word ("exercise", "note") is matched only as its
        # table or a ref; a snake_case kind is never English.
        forms = [rf"\[\[{re.escape(kind)}\]\]", rf"\b{re.escape(kind)}:(?=\S)"]
        if "_" in kind:
            forms.append(rf"\b{re.escape(kind)}\b")
        patterns.append(("record", kind, re.compile("|".join(forms))))
    for view in lexicon["view"]:
        patterns.append(("view", f"query {view}", re.compile(rf"\bquery\s+{re.escape(view)}\b", re.I)))
    for code in lexicon["error"]:
        patterns.append(("error", code, re.compile(rf"\b{re.escape(code)}\b")))
    exits = "|".join(["code"] + [str(n) for n in lexicon["exit"]])
    patterns.append(("error", "exit code", re.compile(rf"\bexit\s+(?:{exits})\b", re.I)))
    prefixes = "|".join(re.escape(p) for p in sorted(lexicon["id_prefix"], key=len, reverse=True))
    store_id = f"(?:{prefixes})\\d+|{STORE_ID_FIXED}" if prefixes else STORE_ID_FIXED
    patterns.append(("store-id", None, re.compile(rf"(?<![\w-])(?:{store_id})\b")))
    patterns.append(("path", None, PATH))
    patterns.append(("hash", None, HASH))
    for term, pattern in FIXED_TERMS.items():
        patterns.append(("fixed", term, pattern))
    return patterns


def voice_leaks(text, patterns):
    """{class: set of matched terms} for one athlete-facing message; URLs are never leaks."""
    text = URL.sub("", text)
    hits = {}
    for held in FENCE.findall(text) + SPAN.findall(FENCE.sub("", text)):
        held = held.strip()
        if held:
            hits.setdefault("code", set()).add(held.splitlines()[0][:60])
    for cls, term, pattern in patterns:
        for match in pattern.finditer(text):
            hits.setdefault(cls, set()).add(term or match.group(0))
    return hits


def measure(path, repo, lexicon):
    first = last = None
    coach_calls = 0
    subcommands = set()
    inline_filters = 0
    inline_filter_calls = 0
    peak_context = 0
    athlete_replies = 0
    skill_chars = 0
    claude_md_chars = 0
    outside_target_chars = 0
    bash_instruction_files = {}
    patterns = leak_patterns(lexicon)
    athlete_messages = 0
    leaking_uuids = []
    leak_hits = {cls: set() for cls in LEAK_CLASSES}
    leaking_by_class = dict.fromkeys(LEAK_CLASSES, 0)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("isSidechain"):
                continue
            ts = rec.get("timestamp")
            if ts:
                t = parse_ts(ts)
                first = t if first is None else min(first, t)
                last = t if last is None else max(last, t)
            kind = rec.get("type")
            if kind == "assistant":
                msg = rec.get("message", {})
                usage = msg.get("usage") or {}
                ctx = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )
                peak_context = max(peak_context, ctx)
                for block in msg.get("content", []) or []:
                    if block.get("type") == "text":
                        athlete_messages += 1
                        hits = voice_leaks(block.get("text", ""), patterns)
                        if hits:
                            leaking_uuids.append(rec.get("uuid"))
                        for cls, terms in hits.items():
                            leak_hits[cls] |= terms
                            leaking_by_class[cls] += 1
                        continue
                    if block.get("type") != "tool_use" or block.get("name") != "Bash":
                        continue
                    cmd = block.get("input", {}).get("command", "")
                    coach_calls += len(COACH_CALL.findall(cmd))
                    for group, command in SUBCOMMAND.findall(cmd):
                        subcommands.add(f"{group} {command}".strip())
                    hits = len(INLINE_PY.findall(cmd))
                    inline_filters += hits
                    inline_filter_calls += 1 if hits else 0
                    for p in INSTRUCTION_PATH.findall(cmd):
                        bash_instruction_files.setdefault(p, None)
            elif kind == "user":
                content = rec.get("message", {}).get("content")
                if isinstance(content, list) and any(c.get("type") == "tool_result" for c in content):
                    continue
                text = text_of(content)
                if text.startswith(SKILL_PREFIX):
                    skill_chars += len(text)
                elif text.strip() and not rec.get("isMeta"):
                    athlete_replies += 1
            elif kind == "attachment":
                att = rec.get("attachment", {})
                if att.get("type") == "instructions":
                    claude_md_chars = 0
                    outside_target_chars = 0
                    for f in att.get("files", []):
                        if f.get("type") in IN_TARGET_INSTRUCTION_TYPES:
                            claude_md_chars += len(f.get("content", ""))
                        else:
                            outside_target_chars += len(f.get("content", ""))
    if repo and last:
        for p in bash_instruction_files:
            bash_instruction_files[p] = file_size_at(repo, last, p)
    bash_chars = sum(v or 0 for v in bash_instruction_files.values())
    instruction_chars = skill_chars + claude_md_chars + bash_chars
    return {
        "session": os.path.basename(path)[:8],
        "wall_minutes": round((last - first).total_seconds() / 60) if first and last else None,
        "coach_calls": coach_calls,
        "distinct_subcommands": len(subcommands),
        "subcommands": sorted(subcommands),
        "inline_filter_calls": inline_filter_calls,
        "inline_filters": inline_filters,
        "peak_context_tokens": peak_context,
        "athlete_replies": athlete_replies,
        "instruction_tokens": round(instruction_chars / CHARS_PER_TOKEN),
        "outside_target_tokens": round(outside_target_chars / CHARS_PER_TOKEN),
        "athlete_messages": athlete_messages,
        "leaking_messages": len(leaking_uuids),
        "leaking_uuids": leaking_uuids,
        "leak_hits": {cls: sorted(terms) for cls, terms in leak_hits.items()},
        "leaking_messages_by_class": leaking_by_class,
        "instruction_chars": {
            "skills": skill_chars,
            "claude_md": claude_md_chars,
            "bash_loaded": bash_instruction_files,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--repo", help="instance repo the sessions ran in (sizes Bash-loaded instruction files)")
    ap.add_argument("--lexicon", help="voice-leak lexicon as a JSON file, in place of reading it from the engine")
    ap.add_argument("--md", action="store_true", help="print the benchmark table as Markdown")
    args = ap.parse_args(argv)
    if args.lexicon:
        with open(args.lexicon, encoding="utf-8") as fh:
            lexicon = json.load(fh)
    else:
        lexicon = build_lexicon(engine_runner())
    rows = [measure(p, args.repo, lexicon) for p in args.sessions]
    if args.md:
        print("| Session | Wall time | coach calls | Distinct subcommands | Bash calls with inline Python | Peak context | Athlete replies | Instruction tokens | Voice leaks |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rows:
            print(
                f"| {r['session']} | {r['wall_minutes']} min | {r['coach_calls']} | {r['distinct_subcommands']} | "
                f"{r['inline_filter_calls']} | {r['peak_context_tokens'] // 1000}k | {r['athlete_replies']} | "
                f"~{round(r['instruction_tokens'] / 1000)}k | {r['leaking_messages']}/{r['athlete_messages']} |"
            )
    else:
        print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
