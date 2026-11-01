"""The Hevy writes a push would make, computed offline from the stored mirrors (ADR 0011,
"Routines and folders"): folders to create, routines to update, create and retire, and exercise
templates to create."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from coach.core.mirror import ENGINE_FOLDER_TITLES, FolderRole
from coach.core.plan_check import TemplateFacts
from coach.core.prescription import PlannedSession, SessionPrescription

type MapStatus = Literal["active", "retired", "missing", "unverified"]

# A routine the map still links to its session; `missing` and `retired` ones are not.
LINKED: frozenset[str] = frozenset({"active", "unverified"})
STANDING_CADENCES = frozenset({"standing", "daily"})


@dataclass(frozen=True)
class MappedRoutine:
    session_id: str
    routine_id: str
    status: MapStatus


@dataclass(frozen=True)
class RoutineAction:
    session_id: str
    routine_id: str | None = None


@dataclass(frozen=True)
class TemplateCreate:
    exercise_id: str
    title: str


@dataclass(frozen=True)
class HevyActions:
    folders: tuple[str, ...] = ()
    updates: tuple[RoutineAction, ...] = ()
    creates: tuple[RoutineAction, ...] = ()
    retires: tuple[RoutineAction, ...] = ()
    templates: tuple[TemplateCreate, ...] = ()

    @property
    def touched_routines(self) -> tuple[str, ...]:
        return tuple(a.routine_id for a in (*self.updates, *self.retires) if a.routine_id)

    @property
    def count(self) -> int:
        return sum(
            len(group)
            for group in (self.folders, self.updates, self.creates, self.retires, self.templates)
        )

    def to_json(self) -> dict[str, object]:
        return {
            "folders_to_create": list(self.folders),
            "routines": {
                "update": [_routine(a) for a in self.updates],
                "create": [_routine(a) for a in self.creates],
                "retire": [_routine(a) for a in self.retires],
            },
            "templates_to_create": [
                {"exercise": t.exercise_id, "title": t.title} for t in self.templates
            ],
        }


def hevy_actions(
    sessions: Sequence[SessionPrescription],
    *,
    routine_map: Sequence[MappedRoutine],
    folders: Collection[FolderRole],
    sessions_in_force: Collection[str],
    templates: Mapping[str, TemplateFacts],
) -> HevyActions:
    """A push projects only the week's planned sessions that carry a line, one routine per
    session however many days it is planned on."""
    projected = _projected(sessions)
    linked = {row.session_id: row for row in routine_map if row.status in LINKED}
    updates = tuple(
        RoutineAction(s.session_id, linked[s.session_id].routine_id)
        for s in projected
        if s.session_id in linked
    )
    creates = tuple(RoutineAction(s.session_id) for s in projected if s.session_id not in linked)
    retires = tuple(
        RoutineAction(row.session_id, row.routine_id)
        for row in linked.values()
        if row.session_id not in sessions_in_force
    )
    needed: list[FolderRole] = []
    if any(not _standing(s) for s in projected):
        needed.append("program")
    if any(_standing(s) for s in projected):
        needed.append("standing")
    if retires:
        needed.append("retired")
    return HevyActions(
        folders=tuple(ENGINE_FOLDER_TITLES[role] for role in needed if role not in folders),
        updates=updates,
        creates=creates,
        retires=retires,
        templates=_templates(sessions, templates),
    )


def _projected(sessions: Sequence[SessionPrescription]) -> tuple[PlannedSession, ...]:
    seen: dict[str, PlannedSession] = {}
    for prescribed in sessions:
        if prescribed.lines:
            seen.setdefault(prescribed.session.session_id, prescribed.session)
    return tuple(seen.values())


def _standing(session: PlannedSession) -> bool:
    return session.cadence in STANDING_CADENCES or session.kind == "rehab"


def _templates(
    sessions: Sequence[SessionPrescription], templates: Mapping[str, TemplateFacts]
) -> tuple[TemplateCreate, ...]:
    found: dict[str, TemplateCreate] = {}
    for prescribed in sessions:
        for line in prescribed.lines:
            facts = templates.get(line.exercise_id)
            if facts is not None and facts.to_create:
                title = str(facts.columns["hevy_title"])
                found.setdefault(line.exercise_id, TemplateCreate(line.exercise_id, title))
    return tuple(found.values())


def _routine(action: RoutineAction) -> dict[str, object]:
    return {"session": action.session_id, "routine": action.routine_id}
