"""Finds coach verbs and raw Hevy calls in one Bash command line.

It reads the shell well enough to find what a command runs, and reports what it cannot read
rather than guess, so an unreadable command reaches a human instead of slipping through.
"""

import os
import posixpath
import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from coach.core.hevy_api import HEVY_HOST


@dataclass(frozen=True)
class CoachCall:
    words: tuple[str, ...]
    cwd: Path
    opaque: bool
    """True when a word is only known once the shell runs, such as `$HASH` or `$(cat f)`."""


@dataclass(frozen=True)
class HevyCall:
    path: str


@dataclass(frozen=True)
class Unreadable:
    why: str


type Finding = CoachCall | HevyCall | Unreadable

MAX_DEPTH = 4
PUNCTUATION = "();<>|&\n"
SEPARATORS = set(";|&()\n")
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
RESERVED_WORDS = frozenset(
    {"if", "then", "elif", "else", "fi", "do", "done", "while", "until", "for", "case", "esac"}
    | {"select", "function", "time", "{", "}", "!", "[[", "]]"}
)
HTTP_CLIENTS = frozenset({"curl", "wget", "http", "https", "xh", "xhs"})
INTERPRETER = re.compile(r"^(python[\d.]*|node|ruby|perl|php|deno|bun)$")
PYTHON = re.compile(r"^python[\d.]*$")
PYTHON_OPTIONS_WITH_VALUE = frozenset({"-X", "-W", "--check-hash-based-pycs"})
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=", re.S)
FD_BEFORE_REDIRECT = re.compile(r"(?<![\w-])\d+(?=[<>])")
HEVY_URL = re.compile(
    re.escape(HEVY_HOST) + r"\.?(?::\d+)?(?P<path>/[^\s'\"`;|&()<>]*)?", re.IGNORECASE
)
SUBSTITUTED = "__coach_hook_substituted__"


def scan(command: str, cwd: Path) -> list[Finding]:
    return list(_scan(command, cwd, 0))


def _scan(text: str, cwd: Path, depth: int) -> Iterator[Finding]:
    if depth > MAX_DEPTH:
        if _mentions(text):
            yield Unreadable("shell commands nested too deeply")
        return
    scripts: list[str] = []
    try:
        tokens = _tokens(_lift_substitutions(text.replace("\\\n", " "), scripts))
    except ValueError as error:
        if _mentions(text):
            yield Unreadable(str(error))
        return
    for script in scripts:
        yield from _scan(script, cwd, depth + 1)
    for words in _simple_commands(tokens):
        words = _unwrapped(words)
        if not words:
            continue
        if os.path.basename(words[0]) in ("cd", "pushd"):
            cwd = _changed_dir(cwd, words[1:])
            continue
        yield from _command(words, text, cwd, depth)


def _command(words: list[str], text: str, cwd: Path, depth: int) -> Iterator[Finding]:
    """What one simple command runs, wherever in it a wrapper such as `timeout 5` puts it."""
    for position in range(len(words)):
        rest = words[position:]
        program = os.path.basename(rest[0])
        nested = _nested_script(rest)
        if nested is not None:
            yield from _scan(nested, cwd, depth + 1)
            return
        argv = _coach_argv(rest)
        if argv and os.path.basename(argv[0]) == "coach":
            continue
        if argv is not None:
            yield CoachCall(tuple(argv), cwd, any(_opaque(word) for word in argv))
            return
        if program in HTTP_CLIENTS or INTERPRETER.match(program):
            for match in HEVY_URL.finditer(" ".join(rest[1:])):
                yield HevyCall(_normalised(match.group("path") or "/"))
            if HEVY_HOST in text.lower() and any(_opaque(word) for word in rest[1:]):
                yield Unreadable("a URL in it is only known when the shell runs it")
            return
    if _opaque(words[0]) and _mentions(text):
        yield Unreadable("the program it runs is only known when the shell runs it")


def _opaque(word: str) -> bool:
    return "$" in word or SUBSTITUTED in word


def _mentions(text: str) -> bool:
    return "coach" in text or HEVY_HOST in text.lower()


def _tokens(text: str) -> list[str]:
    lexer = shlex.shlex(FD_BEFORE_REDIRECT.sub("", text), posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    # Bash keeps `#` inside a word; reading a comment as words can only add an answer.
    lexer.commenters = ""
    lexer.whitespace_split = True
    return list(lexer)


def _lift_substitutions(text: str, scripts: list[str]) -> str:
    """`text` with each `$(...)` and backquoted script outside single quotes moved to `scripts`."""
    out: list[str] = []
    index, single, double = 0, False, False
    while index < len(text):
        char = text[index]
        if single:
            single = char != "'"
        elif char == "\\":
            out.append(text[index : index + 2])
            index += 2
            continue
        elif char == "'" and not double:
            single = True
        elif char == '"':
            double = not double
        elif char == "`" or text.startswith("$(", index):
            begin = index + (1 if char == "`" else 2)
            end = _closing_backquote(text, begin) if char == "`" else _closing_paren(text, begin)
            scripts.append(text[begin:end])
            out.append(SUBSTITUTED)
            index = end + 1
            continue
        out.append(char)
        index += 1
    if single or double:
        raise ValueError("No closing quotation")
    return "".join(out)


def _closing_backquote(text: str, index: int) -> int:
    while index < len(text):
        if text[index] == "`":
            return index
        index += 2 if text[index] == "\\" else 1
    raise ValueError("No closing backquote")


def _closing_paren(text: str, index: int) -> int:
    depth, single, double = 1, False, False
    while index < len(text):
        char = text[index]
        if single:
            single = char != "'"
        elif char == "\\":
            index += 1
        elif char == "'" and not double:
            single = True
        elif char == '"':
            double = not double
        elif char in "()" and not double:
            depth += 1 if char == "(" else -1
            if depth == 0:
                return index
        index += 1
    raise ValueError("No closing parenthesis")


def _simple_commands(tokens: list[str]) -> Iterator[list[str]]:
    """The words of each simple command, split at separators, redirection targets dropped."""
    words: list[str] = []
    skip_target = False
    for token in tokens:
        if skip_target:
            skip_target = False
        elif token and (set(token) <= SEPARATORS or token in ("<(", ">(")):
            if words:
                yield words
            words = []
        elif token and set(token) <= set(PUNCTUATION):
            skip_target = True
        else:
            words.append(token)
    if words:
        yield words


def _unwrapped(words: list[str]) -> list[str]:
    """`words` without leading assignments and reserved words such as `if` or `{`."""
    index = 0
    while index < len(words) and (ASSIGNMENT.match(words[index]) or words[index] in RESERVED_WORDS):
        index += 1
    return words[index:]


def _changed_dir(cwd: Path, args: list[str]) -> Path:
    targets = [arg for arg in args if not arg.startswith("-")]
    if not targets:
        return Path.home()
    return cwd / os.path.expanduser(targets[0])


def _nested_script(words: list[str]) -> str | None:
    """The script of `bash -c '...'` or `eval ...`, else None."""
    name = os.path.basename(words[0])
    if name == "eval":
        return " ".join(words[1:])
    if name not in SHELLS:
        return None
    rest = words[1:]
    for position, option in enumerate(rest):
        if not option.startswith("-") or option.startswith("--"):
            break
        if "c" in option[1:] and position + 1 < len(rest):
            return rest[position + 1]
    return None


def _coach_argv(words: list[str]) -> list[str] | None:
    """The arguments after `coach` or `python -m coach`, else None."""
    program = os.path.basename(words[0])
    if program == "coach":
        return words[1:]
    if not PYTHON.match(program):
        return None
    position = 1
    while position < len(words) and words[position].startswith("-"):
        option = words[position]
        if option == "-mcoach":
            return words[position + 1 :]
        if option == "-m":
            return (
                words[position + 2 :] if words[position + 1 : position + 2] == ["coach"] else None
            )
        if option == "-c":
            return None
        position += 2 if option in PYTHON_OPTIONS_WITH_VALUE else 1
    return None


def _normalised(path: str) -> str:
    path = path.split("?")[0].split("#")[0]
    while unquote(path) != path:
        path = unquote(path)
    return posixpath.normpath(re.sub("/+", "/", path)).lower()
