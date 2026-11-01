"""What `plan apply` reads from the plan Draft: the week, the confirmed rotation position, the
overrides and the acknowledgements (docs/spec/overrides.md, "Draft shape"; docs/spec/validation.md,
"Leaving a warning"). The derived sessions, flags and notes are the engine's context and are
never read back."""

import datetime
import tomllib
from dataclasses import dataclass
from typing import cast

from coach.core.draft_fields import Fields, required
from coach.core.errors import Invalid
from coach.core.flag import Acknowledgement, FlagKey
from coach.core.overrides import parse_plan_overrides
from coach.core.prescription import PlanOverride
from coach.core.registries.flags import FLAGS
from coach.core.registries.ledger import REASONS, Reason

ENGINE_CONTEXT = ("supersedes", "flag", "session", "note")


@dataclass(frozen=True)
class PlanInput:
    week: datetime.date
    position: str | None
    overrides: tuple[PlanOverride, ...]
    acknowledgements: tuple[Acknowledgement, ...]


def parse_plan_input(data: bytes, *, file: str) -> PlanInput:
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Invalid("invalid_argument", f"{file} is not a TOML plan Draft: {error}") from error
    top = Fields(document, file)
    week = required(top.date("week", required=True))
    position = _position(top.subtable("position"))
    top.raw("override")
    overrides = parse_plan_overrides(document, file=file)
    acknowledgements = tuple(_acknowledge(f) for f in top.tables("acknowledge"))
    for name in ENGINE_CONTEXT:
        top.raw(name)
    return top.done(PlanInput(week, position, overrides, acknowledgements))


def _position(f: Fields | None) -> str | None:
    if f is None:
        return None
    week = f.text("week", required=True)
    f.text("source")
    confirmed = f.boolean("confirmed")
    return f.done(week if confirmed else None)


def _acknowledge(f: Fields) -> Acknowledgement:
    text = required(f.text("flag", required=True))
    key = FlagKey.parse(text)
    if key.code not in FLAGS or FLAGS.get(key.code).severity != "warning":
        raise f.wrong("flag", "the key of a warning: a violation is never left (validation.md)")
    if "weekplan" not in FLAGS.get(key.code).left_by:
        raise f.wrong("flag", f"a warning a plan leaves; {key.code} is not raised on a plan")
    return f.done(
        Acknowledgement(
            key,
            required(f.text("params_hash", required=True)),
            cast(Reason, f.term("because", REASONS, required=True)),
            required(f.text("text", required=True)),
            tuple(str(ref) for ref in f.refs("evidence")),
        )
    )
