from pathlib import Path

import pytest
from support.cli import run_coach
from support.raised_codes import raised_with

from coach.cli import registry
from coach.cli.declaration import Call, Declaration, Outcome
from coach.core.errors import Invalid, Refused, Setup, Unreachable
from coach.core.registries.errors import ERRORS, ErrorClass

SRC = Path(__file__).resolve().parents[2] / "src"

CLASS_OF: dict[str, ErrorClass] = {
    "Invalid": "invalid",
    "Refused": "refused",
    "Unreachable": "unreachable",
    "Setup": "setup",
    "Message": "internal",
}


def mismatches(src: Path, rows: dict[str, ErrorClass]) -> list[str]:
    """Each raised code with no row or the wrong class, and each row nothing raises."""
    raised = raised_with(src, frozenset(CLASS_OF))
    problems = [
        f"{code} raised as {CLASS_OF[builder]} at {', '.join(sites)}, registry says "
        f"{rows.get(code)}"
        for code, builders in sorted(raised.items())
        for builder, sites in builders.items()
        if rows.get(code) != CLASS_OF[builder]
    ]
    problems += [f"{code} is a row nothing raises" for code in sorted(set(rows) - set(raised))]
    return problems


def registry_rows() -> dict[str, ErrorClass]:
    return {row.name: row.error_class for row in ERRORS.entries}


def test_every_raised_code_is_a_row_of_the_class_it_is_raised_with() -> None:
    assert mismatches(SRC, registry_rows()) == []


def plant(root: Path, source: str) -> Path:
    module = root / "coach" / "services" / "x.py"
    module.parent.mkdir(parents=True)
    module.write_text(source, encoding="utf-8")
    return root


def test_a_code_with_no_row_is_reported_with_its_site(tmp_path: Path) -> None:
    src = plant(tmp_path, 'def f():\n    raise Setup("made_up", "x")\n')

    assert mismatches(src, {}) == [
        "made_up raised as setup at coach/services/x.py:2, registry says None"
    ]


def test_a_code_raised_with_another_class_is_reported(tmp_path: Path) -> None:
    src = plant(tmp_path, 'def f():\n    raise Refused("no_instance", "x")\n')

    assert mismatches(src, {"no_instance": "setup"}) == [
        "no_instance raised as refused at coach/services/x.py:2, registry says setup"
    ]


def test_a_message_code_is_internal_and_a_row_nothing_raises_is_reported(
    tmp_path: Path,
) -> None:
    src = plant(tmp_path, 'def f():\n    return Message("internal_error", "x")\n')

    assert mismatches(src, {"internal_error": "internal", "gone": "invalid"}) == [
        "gone is a row nothing raises"
    ]


def exit_of(error: Exception, monkeypatch: pytest.MonkeyPatch) -> int:
    def fail(call: Call) -> Outcome:
        raise error

    failing = Declaration(name="fail", summary="Fails.", writes="none", output={}, run=fail)
    monkeypatch.setattr(registry, "declarations", lambda: (failing,))
    return run_coach("fail").code


@pytest.mark.parametrize(
    ("error", "error_class"),
    [
        (Invalid("c", "m"), "invalid"),
        (Refused("c", "m"), "refused"),
        (Unreachable("c", "m"), "unreachable"),
        (Setup("c", "m"), "setup"),
        (RuntimeError("boom"), "internal"),
    ],
)
def test_each_class_exits_as_the_engine_does(
    monkeypatch: pytest.MonkeyPatch, error: Exception, error_class: ErrorClass
) -> None:
    exits = {row.exit for row in ERRORS.entries if row.error_class == error_class}

    assert exits == {exit_of(error, monkeypatch)}
