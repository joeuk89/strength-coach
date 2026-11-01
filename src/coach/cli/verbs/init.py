import os
import re
from pathlib import Path

from coach.cli import git, init_answers, registry
from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.core.config import Config, Engine, Hevy
from coach.core.errors import Invalid, Setup
from coach.render.instance_files import GITIGNORE, claude_md, coach_toml, settings_json
from coach.store.connection import open_store

RELEASE_VERSION = re.compile(r"\d+\.\d+\.\d+")
# The engine-owned tier of ADR 0013, plus the append-only audit.
ENGINE_OWNED = (
    "coach.toml",
    "CLAUDE.md",
    ".claude/settings.json",
    "README.md",
    "pages",
    "export",
    ".coach",
    "hevy/writes.jsonl",
)
STORE = ".coach/coach.db"
DIRECTORIES = ("kit/", ".coach/drafts/")
NEXT_STEP = (
    "create an empty remote repository, then `git remote add origin <url>` and "
    "`git push -u origin HEAD`"
)


def run(call: Call) -> Outcome:
    root = Path.cwd()
    _refuse_an_instance(root)
    args = call.args
    pin = _pin(call.engine_version, args.get("pin"))
    defaults = args.get("defaults") is True
    missing = init_answers.missing_flags(args)
    if missing and not defaults and not call.terminal.interactive:
        raise Invalid(
            "invalid_argument",
            f"init needs {', '.join(missing)}; pass them, pass --defaults, or run it in a terminal",
        )
    athlete = init_answers.athlete(args, defaults=defaults, terminal=call.terminal, env=call.env)
    hevy = init_answers.hevy(args, defaults=defaults, terminal=call.terminal)
    config = Config(engine=Engine(pin), athlete=athlete, hevy=Hevy() if hevy.on else None)
    texts = _texts(root, config, pin, hevy.key)
    files = [*texts, *DIRECTORIES, STORE]
    summary: Json = {"pin": pin, "hevy": {"on": hevy.on}, "files": files}
    git_init = not git.is_repo(root)
    if args.get("dry_run") is True:
        return Outcome({"dry_run": True, **summary, "git_init": git_init})
    git.check_can_commit(root)
    if call.terminal.interactive:
        call.terminal.say("coach init will write:\n" + "\n".join(f"  {f}" for f in files))
        if not call.terminal.confirm("Write these files and commit them?"):
            return Outcome({"declined": True, **summary})
    if git_init:
        git.init(root)
    _write(root, texts)
    committed = [path for path in texts if path != ".env"]
    commit = git.commit(root, committed, f"coach init v{pin}")
    return Outcome(
        {
            **summary,
            "git_init": git_init,
            "commit": commit,
            "committed": committed,
            "next": NEXT_STEP,
        }
    )


def _refuse_an_instance(root: Path) -> None:
    found = [path for path in ENGINE_OWNED if (root / path).exists()]
    if found:
        raise Setup(
            "instance_exists",
            f"{root} already holds engine-owned {', '.join(found)}; init writes only a new "
            "instance, `coach upgrade` moves an existing one",
        )


def _pin(running: str, requested: str | bool | None) -> str:
    if isinstance(requested, str) and not RELEASE_VERSION.fullmatch(requested):
        raise Invalid("invalid_argument", f"--pin takes a release X.Y.Z, not {requested!r}")
    if ".dev" in running:
        if not isinstance(requested, str):
            raise Setup(
                "engine_pin_required",
                f"engine {running} is a development build; pass --pin X.Y.Z, the release "
                "this instance will run",
            )
        return requested
    if isinstance(requested, str) and requested != running:
        raise Setup(
            "engine_pin_mismatch",
            f"engine {running} pins an instance to itself; --pin {requested} differs",
        )
    return running


def _texts(root: Path, config: Config, pin: str, key: str | None) -> dict[str, str]:
    asked = [d.name for d in registry.declarations() if d.writes in ("hevy", "git")]
    texts = {
        ".gitignore": _gitignore(root / ".gitignore"),
        ".claude/settings.json": settings_json(asked),
        "CLAUDE.md": claude_md(pin),
        "coach.toml": coach_toml(config),
    }
    if key is not None:
        if (root / ".env").exists():
            raise Invalid("invalid_argument", f"{root / '.env'} exists; drop --hevy-key or it")
        texts[".env"] = f"HEVY_API_KEY={key}\n"
    return texts


def _gitignore(path: Path) -> str:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    have = set(existing.splitlines())
    added = [line for line in GITIGNORE.splitlines() if line not in have]
    if existing and not existing.endswith("\n"):
        existing += "\n"
    return existing + "".join(f"{line}\n" for line in added)


def _write(root: Path, texts: dict[str, str]) -> None:
    for relative, text in texts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if relative == ".env":
            os.chmod(path, 0o600)
    for directory in DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)
    open_store(root / STORE).close()


ANSWER_ARGUMENTS = tuple(
    Argument(question.flag, f"{question.prompt.lower()}; asked on a terminal")
    for question in init_answers.QUESTIONS
)

DECLARATION = Declaration(
    name="init",
    summary="Create an instance in this directory: coach.toml, the generated files, an empty "
    "store, one commit.",
    writes="git",
    needs_instance=False,
    arguments=(
        Argument(
            "--dry-run", "print the tree init would write and touch nothing", takes_value=False
        ),
        Argument("--pin", "the release X.Y.Z the instance runs; required on a .dev engine"),
        Argument("--defaults", "take the default for every answer not given", takes_value=False),
        *ANSWER_ARGUMENTS,
        Argument("--hevy", "yes or no: whether workouts are logged in Hevy"),
        Argument(
            "--hevy-key", "the Hevy API key, written to the gitignored .env; implies --hevy yes"
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "pin": {"type": "string"},
            "hevy": {"type": "object", "properties": {"on": {"type": "boolean"}}},
            "files": {"type": "array", "items": {"type": "string"}},
            "git_init": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
            "declined": {"type": "boolean"},
            "commit": {"type": "string"},
            "committed": {"type": "array", "items": {"type": "string"}},
            "next": {"type": "string"},
        },
        "required": ["pin", "hevy", "files"],
    },
    run=run,
    examples=(
        Example(
            ("init", "--dry-run", "--defaults", "--pin", "1.0.0"), "The tree init would write."
        ),
        Example(
            ("init", "--pin", "1.0.0"), "Ask each answer on the terminal, then write and commit."
        ),
    ),
)
