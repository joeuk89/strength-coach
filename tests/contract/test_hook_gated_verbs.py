import pytest
from support.hook import DECLARATIONS, a_bash_call, a_declaration, run_hook

from coach.cli.declaration import Declaration
from coach.cli.registry import declarations

EVERY_DECLARATION = [*declarations(), *DECLARATIONS]


def a_command(declaration: Declaration) -> str:
    required = [f"{a.key}.toml" for a in declaration.arguments if a.positional and a.required]
    return " ".join(["coach", declaration.name, *required])


@pytest.mark.parametrize("declaration", EVERY_DECLARATION, ids=lambda d: d.name)
def test_the_hook_runs_the_dry_run_of_exactly_the_verbs_declared_hevy_git_or_github(
    declaration: Declaration,
) -> None:
    run = run_hook("pre-tool-use", a_bash_call(a_command(declaration)), declarations=[declaration])

    gated = declaration.writes in ("hevy", "git", "github")
    assert (run.decision is not None) == gated
    assert (len(run.dry_runs) == 1) == gated


def test_a_new_declaration_writing_hevy_is_gated_with_no_change_to_the_hook() -> None:
    added = a_declaration("program adopt", "hevy")

    run = run_hook("pre-tool-use", a_bash_call("coach program adopt"), declarations=[added])

    assert run.decision == "ask"
    assert run.dry_runs[0][0] == ["program", "adopt", "--dry-run"]
