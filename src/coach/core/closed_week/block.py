"""The Block, derived from closed weeks and redesign adoptions, never stored (ADR 0018;
docs/spec/week.md, "The Block")."""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass, replace

from coach.core.closed_week.kind import WeekKind
from coach.core.flag import Flag, Scope, raise_flag

CLOSING_KINDS: tuple[WeekKind, ...] = ("light", "return", "missed")


@dataclass(frozen=True)
class Block:
    """`weeks` counts the closed weeks inside it, `hard_weeks` the `hard` ones; `closed_by` is
    the closing week's kind or `redesign`, and `None` while it is open."""

    id: str
    opened: datetime.date
    hard_weeks: int = 0
    weeks: int = 0
    closed_by: str | None = None


def blocks(
    weeks: Sequence[tuple[datetime.date, WeekKind]], redesigns: Sequence[datetime.date]
) -> tuple[Block, ...]:
    """Every Block in order, the open one last. A redesign opens a Block on its adoption date
    and takes the weeks whose Monday falls on or after it; a closing week opens the next Block
    on the following Monday."""
    pending = sorted(redesigns)
    found: list[Block] = []

    def open_at(day: datetime.date) -> None:
        if found and found[-1].closed_by is None:
            if found[-1].weeks == 0 and len(found) > 1:
                found.pop()
            else:
                found[-1] = replace(found[-1], closed_by="redesign")
        found.append(Block(f"b-{day.isoformat()}", day))

    for monday, kind in sorted(weeks):
        while pending and pending[0] <= monday:
            open_at(pending.pop(0))
        if not found:
            continue
        block = found[-1]
        if kind in CLOSING_KINDS:
            found[-1] = replace(block, weeks=block.weeks + 1, closed_by=kind)
            following = monday + datetime.timedelta(weeks=1)
            found.append(Block(f"b-{following.isoformat()}", following))
        else:
            hard = block.hard_weeks + (1 if kind == "hard" else 0)
            found[-1] = replace(block, hard_weeks=hard, weeks=block.weeks + 1)
    for day in pending:
        open_at(day)
    return tuple(found)


def block_ceiling_exceeded(
    block: Block,
    ceiling: int,
    monday: datetime.date,
    *,
    light_week: bool = False,
    declined: bool = False,
) -> Flag | None:
    """The plan of a week whose open Block has reached the version's ceiling, unless it takes
    the light week or a `decline_ceiling` names the Block (rn:deloads.3)."""
    if block.hard_weeks < ceiling or light_week or declined:
        return None
    return raise_flag(
        "block_ceiling_exceeded",
        Scope("week", monday),
        {"hard_weeks": block.hard_weeks, "ceiling": ceiling, "block_id": block.id},
        f"{block.id} has {block.hard_weeks} hard weeks against a ceiling of {ceiling}; "
        "take a light week, decline it with a Decision, or adopt a redesign",
    )
