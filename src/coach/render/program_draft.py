from typing import cast

from coach.core.program.form import ProgramForm
from coach.render.toml import TomlValue, dumps


def program_draft(form: ProgramForm) -> str:
    """The version as a Draft to edit: an `amend` of it, filled defaults written out
    (program.md, "Adopt")."""
    document = form.to_document()
    document["kind"] = "amend"
    return dumps(cast(dict[str, TomlValue], document))
