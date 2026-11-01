from typing import cast

from coach.core.program.form import ProgramForm
from coach.render.toml import Commented, TomlValue, dumps

FOLDED_PIN = "folded pin"


def program_draft(
    form: ProgramForm, *, folded_pins: frozenset[tuple[str, str]] = frozenset()
) -> str:
    """The version as a Draft to edit: an `amend` of it, filled defaults written out, and each
    `start_load` a WeekPlan's pin folded into labelled (program.md, "Adopt")."""
    document = form.to_document()
    document["kind"] = "amend"
    for session in cast(list[dict[str, object]], document["session"]):
        for line in cast(list[dict[str, object]], session.get("line", [])):
            if (session["id"], line["exercise"]) in folded_pins:
                line["start_load"] = Commented(cast(TomlValue, line["start_load"]), FOLDED_PIN)
    return dumps(cast(dict[str, TomlValue], document))
