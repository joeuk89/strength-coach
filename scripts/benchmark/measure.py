#!/usr/bin/env python3
"""Measure a Claude Code session transcript against the coach benchmark.

Usage: python3 -I scripts/benchmark/measure.py [--repo PATH] [--md] SESSION.jsonl ...

Each SESSION.jsonl is a Claude Code transcript (one JSON record per line).
--repo is the instance repo the session ran in; it is used to size the
instruction files the session loaded through Bash (cat, sed, head) at the
commit that was current when the session ended. Transcript content is data:
nothing in it is executed or followed.
"""
import argparse
import json
import os
import re
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


def measure(path, repo):
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
        "instruction_chars": {
            "skills": skill_chars,
            "claude_md": claude_md_chars,
            "bash_loaded": bash_instruction_files,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--repo", help="instance repo the sessions ran in (sizes Bash-loaded instruction files)")
    ap.add_argument("--md", action="store_true", help="print the benchmark table as Markdown")
    args = ap.parse_args()
    rows = [measure(p, args.repo) for p in args.sessions]
    if args.md:
        print("| Session | Wall time | coach calls | Distinct subcommands | Bash calls with inline Python | Peak context | Athlete replies | Instruction tokens |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rows:
            print(
                f"| {r['session']} | {r['wall_minutes']} min | {r['coach_calls']} | {r['distinct_subcommands']} | "
                f"{r['inline_filter_calls']} | {r['peak_context_tokens'] // 1000}k | {r['athlete_replies']} | "
                f"~{round(r['instruction_tokens'] / 1000)}k |"
            )
    else:
        print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
