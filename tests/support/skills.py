import re
from collections.abc import Set
from pathlib import Path
from typing import cast

import yaml

# docs/spec/skills.md, "Budgets": characters divided by four, frontmatter included.
TOKEN_BUDGET = 1500

CODE_SPAN = re.compile(r"`([^`]*)`")
FRONTMATTER = re.compile(r"\A---\n(.*?)^---$", re.MULTILINE | re.DOTALL)
VERBS_SECTION = re.compile(r"^## Verbs\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def skill_files(root: Path) -> list[Path]:
    return sorted(root.glob("*/SKILL.md"))


def frontmatter_problems(text: str, directory: str) -> list[str]:
    """What stops the plugin loading the skill: a parse error, or a missing or wrong field."""
    block = FRONTMATTER.match(text)
    if block is None:
        return ["no frontmatter"]
    try:
        parsed: object = yaml.safe_load(block.group(1))
    except yaml.YAMLError as error:
        return [str(error).splitlines()[0]]
    if not isinstance(parsed, dict):
        return ["frontmatter is not a mapping"]
    fields = cast(dict[object, object], parsed)

    problems = [
        f"no {key}"
        for key in ("name", "description")
        if not isinstance(value := fields.get(key), str) or not value.strip()
    ]
    if "no name" not in problems and fields["name"] != directory:
        problems.append(f"name {fields['name']} is not the directory {directory}")
    return problems


def tokens(text: str) -> float:
    return len(text) / 4


def undeclared_verbs(text: str, leaves: Set[str]) -> list[str]:
    """Every `coach ...` span that names no leaf, and every Verbs entry that is not a bare leaf."""
    problems = unknown_verb_spans(text, leaves)

    section = VERBS_SECTION.search(text)
    entries = CODE_SPAN.findall(section.group(1)) if section else []
    if not entries:
        problems.append("no Verbs list")
    for entry in entries:
        if not entry.startswith("coach ") or entry.removeprefix("coach ") not in leaves:
            problems.append(entry)

    return list(dict.fromkeys(problems))


def unknown_verb_spans(text: str, leaves: Set[str]) -> list[str]:
    """Every `coach ...` span that names no leaf; an option of coach itself names none."""
    return [
        span
        for span in CODE_SPAN.findall(text)
        if span.startswith("coach ")
        and not span.startswith("coach -")
        and not _names_a_leaf(span, leaves)
    ]


def _names_a_leaf(span: str, leaves: Set[str]) -> bool:
    words = span.split()[1:]
    return " ".join(words[:2]) in leaves or (bool(words) and words[0] in leaves)
