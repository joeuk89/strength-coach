from pathlib import Path

from support.raised_codes import raised_codes

from coach.core.registries.flags import FLAGS

SRC = Path(__file__).resolve().parents[2] / "src"

# The refusal reasons verbs.md's exit classes name.
REFUSALS = frozenset(
    {
        "invalid_argument",
        "state_conflict",
        "priority_lift_duplicate",
        "milestone_target_missing",
        "phase_already_open",
        "draft_exists",
        "verify_failed",
        "expect_missing",
        "expect_mismatch",
        "routine_moved",
        "folder_title_shared",
        "audit_unwritable",
        "hevy_unreachable",
        "github_unreachable",
        "instance_exists",
        "env_file_exists",
        "git_tree_dirty",
        "engine_pin_required",
        "git_unavailable",
        "git_identity_missing",
        "git_commit_failed",
        "git_failed",
        "engine_pin_mismatch",
        "no_instance",
        "schema_behind",
        "hevy_key_missing",
        "github_token_missing",
        "config_unknown_key",
        "kit_tables_stale",
        "export_newer_than_engine",
        "jsonl_row_malformed",
        "store_behind_export",
    }
)


def unnamed(sites: dict[str, list[str]]) -> dict[str, list[str]]:
    known = REFUSALS | set(FLAGS.names())
    return {code: where for code, where in sites.items() if code not in known}


def test_every_raised_code_is_a_named_refusal_or_a_registry_flag() -> None:
    assert unnamed(raised_codes(SRC)) == {}


def test_a_code_outside_both_lists_is_reported_with_its_site(tmp_path: Path) -> None:
    module = tmp_path / "coach" / "services" / "x.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "def f():\n"
        '    raise Invalid("invalid_argument", "fine")\n'
        "def g():\n"
        '    raise Refused("made_up", "not in verbs.md")\n',
        encoding="utf-8",
    )

    assert unnamed(raised_codes(tmp_path)) == {"made_up": ["coach/services/x.py:4"]}
