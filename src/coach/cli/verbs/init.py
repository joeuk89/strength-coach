import os
from contextlib import closing
from pathlib import Path

from coach.cli import git, init_answers
from coach.cli.declaration import (
    Argument,
    ArgValue,
    Call,
    Declaration,
    Example,
    Instance,
    Json,
    Outcome,
)
from coach.cli.generated import generated_files
from coach.cli.hevy_key import find_key
from coach.cli.pull import PULL_SCHEMA, Pulled, pull, with_pull
from coach.core.config import Config, Engine, Hevy
from coach.core.engine_pin import is_release
from coach.core.errors import Invalid, Setup, Unreachable
from coach.render.instance_files import GITIGNORE, coach_toml
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

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
        keyed = hevy.key or find_key(call.env, root / ".env")
        pulls = " and then pull the Hevy history" if hevy.on and keyed else ""
        call.terminal.say(f"coach init will write{pulls}:\n" + "\n".join(f"  {f}" for f in files))
        if not call.terminal.confirm("Write these files and commit them?"):
            return Outcome({"declined": True, **summary})
    if git_init:
        git.init(root)
    _write(root, texts)
    committed = [path for path in texts if path != ".env"]
    commit = git.commit(root, committed, f"coach init v{pin}")
    pulled = _first_pull(call, Instance(root, config))
    result: Json = {
        **summary,
        "git_init": git_init,
        "commit": commit,
        "committed": committed,
        "next": NEXT_STEP,
    }
    return with_pull(Outcome(result), pulled)


def _first_pull(call: Call, instance: Instance) -> Pulled | None:
    """The full pull of the Hevy history, run after the commit so a failed one leaves the
    instance written for the next pulling verb to complete. With no key yet, that verb pulls."""
    if instance.config.hevy is None or find_key(call.env, instance.root / ".env") is None:
        return None
    clock = call.make_clock(instance.config.athlete.timezone)
    try:
        with closing(open_store(instance.store_path)) as conn:
            return pull(call, conn, instance, clock)
    except Unreachable as error:
        raise Unreachable(
            error.code,
            f"{error.message}; the instance is written and committed, and the next verb that "
            "reads workouts pulls the history",
        ) from error


def _refuse_an_instance(root: Path) -> None:
    found = [path for path in ENGINE_OWNED if (root / path).exists()]
    if found:
        raise Setup(
            "instance_exists",
            f"{root} already holds engine-owned {', '.join(found)}; init writes only a new "
            "instance, `coach upgrade` moves an existing one",
        )


def _pin(running: str, requested: ArgValue | None) -> str:
    if isinstance(requested, str) and not is_release(requested):
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
    texts = {
        ".gitignore": _gitignore(root / ".gitignore"),
        **generated_files(pin),
        "coach.toml": coach_toml(config),
    }
    if key is not None:
        if (root / ".env").exists():
            raise Setup("env_file_exists", f"{root / '.env'} exists; drop --hevy-key or it")
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
    with closing(open_store(root / STORE)) as conn, conn:
        seed_catalogue(conn)


ANSWER_ARGUMENTS = tuple(
    Argument(question.flag, f"{question.prompt.lower()}; asked on a terminal")
    for question in init_answers.QUESTIONS
)

DECLARATION = Declaration(
    name="init",
    summary="Create an instance in this directory: coach.toml, the generated files, the store, "
    "one commit; with Hevy on and a key, then pull the whole Hevy history into the store.",
    writes="git",
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
            "pull": PULL_SCHEMA,
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
