import re
from collections.abc import Set
from pathlib import Path

# docs/spec/skills.md, "Budgets": characters divided by four, frontmatter included.
TOKEN_BUDGET = 1500

CODE_SPAN = re.compile(r"`([^`]*)`")
VERBS_SECTION = re.compile(r"^## Verbs\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def skill_files(root: Path) -> list[Path]:
    return sorted(root.glob("*/SKILL.md"))


def tokens(text: str) -> float:
    return len(text) / 4


def undeclared_verbs(text: str, leaves: Set[str]) -> list[str]:
    """Every `coach ...` span that names no leaf, and every Verbs entry that is not a bare leaf."""
    problems: list[str] = []
    for span in CODE_SPAN.findall(text):
        if span.startswith("coach ") and not _names_a_leaf(span, leaves):
            problems.append(span)

    section = VERBS_SECTION.search(text)
    entries = CODE_SPAN.findall(section.group(1)) if section else []
    if not entries:
        problems.append("no Verbs list")
    for entry in entries:
        if not entry.startswith("coach ") or entry.removeprefix("coach ") not in leaves:
            problems.append(entry)

    return list(dict.fromkeys(problems))


def _names_a_leaf(span: str, leaves: Set[str]) -> bool:
    words = span.split()[1:]
    return " ".join(words[:2]) in leaves or (bool(words) and words[0] in leaves)
