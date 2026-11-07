"""PROTOTYPE (wayfinder #228): the voice-leak lexicon of #226, enough to score a reply.

Derived from the engine at run time (`uv run coach`), plus the fixed list and patterns.
Throwaway; the real count is #233 in measure.py.
"""
import json
import re
import subprocess
from functools import lru_cache

REPO = "/Users/joeabousselam/personal/strength-coach"

ERROR_CODES = [
    "invalid_argument", "state_conflict", "draft_ref_unresolved", "hevy_unreachable", "git_failed",
    "config_unknown_key", "unknown_key", "no_instance", "kit_tables_stale", "jsonl_row_malformed",
    "git_unavailable", "env_file_exists", "engine_pin_mismatch", "unknown_exercise", "draft_exists",
    "internal_error",
]

FIXED = [
    r"\bDraft\b", r"\benvelope\b", r"\bthe store\b", r"\bdry[- ]run\b", r"\bverbs?\b", r"\bflags?\b",
    r"\bschema\b", r"\bregistry\b", r"\bread view\b", r"\bthe engine\b", r"\bthe repo\b",
    r"\backnowledgements?\b", r"\bexit code\b",
]

PATTERNS = {
    "path": re.compile(r"(?:(?:\.coach|pages|src|export)/[\w./-]+|\b[\w-]+\.(?:toml|py|jsonl|md)\b)"),
    "store_id": re.compile(r"\b(?:pv-\d+|b-\d{4}-\d{2}-\d{2}|wp-\d{4}-\d{2}-\d{2})\b"),
    "hash": re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"),
    "code": re.compile(r"```|`[^`\n]+`"),
    "exit": re.compile(r"\bexit (?:code|[1345])\b"),
}


def _coach(*args):
    out = subprocess.check_output(["uv", "run", "--project", REPO, "coach", *args], text=True, stderr=subprocess.DEVNULL, cwd=REPO)
    return json.loads(out)["result"]


@lru_cache(maxsize=None)
def build():
    verbs = [v["name"] for v in _coach("--help")["verbs"]]
    flags = [r["code"] for r in _coach("schema", "--registry", "flags", "--full")["rows"]]
    views = [r["name"] for r in _coach("schema", "--registry", "views")["rows"]]
    verb_res = []
    for v in verbs:
        if " " in v:
            verb_res.append(r"\b" + re.escape(v) + r"\b")
        verb_res.append(r"\bcoach " + re.escape(v) + r"\b")
    classes = {
        "verb": re.compile("|".join(verb_res), re.I),
        "flag": re.compile(r"\b(?:" + "|".join(map(re.escape, flags)) + r")\b"),
        "view": re.compile(r"\bquery (?:" + "|".join(map(re.escape, views)) + r")\b"),
        "error": re.compile(r"\b(?:" + "|".join(map(re.escape, ERROR_CODES)) + r")\b"),
        "fixed": re.compile("|".join(FIXED)),
    }
    classes.update(PATTERNS)
    return classes


def hits(text):
    """Class -> sorted distinct terms matched. Empty dict means no leak."""
    found = {}
    for cls, rx in build().items():
        terms = sorted({m.group(0) for m in rx.finditer(text)})
        if terms:
            found[cls] = terms
    return found


if __name__ == "__main__":
    import sys
    print(json.dumps(hits(sys.stdin.read()), indent=1))
