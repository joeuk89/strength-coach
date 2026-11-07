from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from coach.core.registries.registry import Registry, Row

type ErrorClass = Literal["invalid", "refused", "unreachable", "setup", "internal"]

# The first four are `EXIT_CLASSES` in `cli/app.py`; `internal` is what `main` returns for an
# uncaught exception. Core cannot import `cli`, so a contract test keeps them equal.
EXITS: Mapping[ErrorClass, int] = {
    "invalid": 1,
    "refused": 3,
    "unreachable": 4,
    "setup": 5,
    "internal": 1,
}


@dataclass(frozen=True)
class ErrorCode:
    name: str
    error_class: ErrorClass
    summary: str

    @property
    def exit(self) -> int:
        return EXITS[self.error_class]

    def describe(self) -> Row:
        return {
            "code": self.name,
            "class": self.error_class,
            "exit": self.exit,
            "summary": self.summary,
        }


def _invalid(name: str, summary: str) -> ErrorCode:
    return ErrorCode(name, "invalid", summary)


def _refused(name: str, summary: str) -> ErrorCode:
    return ErrorCode(name, "refused", summary)


def _setup(name: str, summary: str) -> ErrorCode:
    return ErrorCode(name, "setup", summary)


# docs/spec/verbs.md, "Exit classes".
ERRORS = Registry(
    "errors",
    (
        _invalid(
            "invalid_argument",
            "An unknown or ill-typed argument, a field that does not parse, or an unreadable file.",
        ),
        _invalid("state_conflict", "Well-formed input that stored state or a rule forbids."),
        _invalid("draft_exists", "An explicit --out names a Draft that already exists."),
        _invalid("draft_ref_unresolved", "A Draft refers to a row that is not stored."),
        _invalid("duplicate_id", "A Draft or the ledger repeats an id."),
        _invalid("hevy_template_missing", "An exercise has no Hevy template to write it with."),
        _invalid("milestone_target_missing", "A goal milestone has no target."),
        _invalid("niggle_constraint_on_resolved", "A constraint is added to a resolved niggle."),
        _invalid("phase_already_open", "A [phase] opens while another phase is open."),
        _invalid("priority_lift_duplicate", "A goal names a priority lift twice."),
        _invalid("reading_duplicate", "A reading repeats one already stored for that day."),
        _invalid("record_kind_not_allowed", "A Draft carries a record kind its verb refuses."),
        _invalid("unknown_exercise", "An exercise id the store does not hold."),
        _invalid("unknown_key", "A Draft table or key the parser does not know."),
        _invalid("verify_failed", "A routine read back from Hevy differs from what was written."),
        _refused("expect_missing", "plan apply runs without --expect."),
        _refused("expect_mismatch", "plan apply's --expect hash differs from the dry run's."),
        _refused("routine_moved", "A routine moved in Hevy since the import."),
        _refused("folder_title_shared", "Two Hevy folders share the title of a folder to adopt."),
        _refused("audit_unwritable", "The write audit cannot be opened for append."),
        ErrorCode(
            "hevy_unreachable",
            "unreachable",
            "Hevy cannot be reached or answers with a payload the client cannot read.",
        ),
        ErrorCode(
            "github_unreachable",
            "unreachable",
            "GitHub cannot be reached or answers report with anything but the issue it filed.",
        ),
        _setup("instance_exists", "init runs where an instance already is."),
        _setup("engine_pin_required", "init on a .dev build without --pin."),
        _setup("env_file_exists", "init runs where a .env already exists."),
        _setup("git_unavailable", "git is not on the PATH."),
        _setup("git_identity_missing", "git knows no committer."),
        _setup("git_tree_dirty", "upgrade on a git tree with uncommitted changes."),
        _setup("git_commit_failed", "git refuses the commit."),
        _setup("git_failed", "A git step other than the commit fails."),
        _setup("engine_pin_mismatch", "The engine is not the version the instance pins."),
        _setup("no_instance", "The verb runs outside an instance."),
        _setup("schema_behind", "The store's schema is behind the engine's."),
        _setup("hevy_key_missing", "A [hevy] table with no key in the environment or .env."),
        _setup("github_token_missing", "report runs with no token in the environment or .env."),
        _setup("config_unknown_key", "coach.toml holds an unknown table or key."),
        _setup("kit_tables_stale", "A location's kit tables are missing or behind its inventory."),
        _setup("export_newer_than_engine", "The export was written by a newer engine."),
        _setup("jsonl_row_malformed", "An export row does not parse."),
        _setup("store_behind_export", "The store is behind the export it was built from."),
        ErrorCode("internal_error", "internal", "An unexpected failure inside the engine."),
    ),
)
