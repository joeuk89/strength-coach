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

LINKED: frozenset[str] = frozenset({"active", "unverified"})
STANDING_CADENCES = frozenset({"standing", "daily"})


@dataclass(frozen=True)
class MappedRoutine:
    session_id: str
    routine_id: str
    status: MapStatus
    written_at: str = ""


@dataclass(frozen=True)
class ProjectedSession:
    """A planned session the push gives a routine, and the exercises its lines name."""

    session_id: str
    standing: bool
    exercises: tuple[str, ...] = ()


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
        """Every routine a PUT would overwrite, a spare a create takes included."""
        return tuple(
            a.routine_id for a in (*self.updates, *self.creates, *self.retires) if a.routine_id
        )

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
    projected: Sequence[ProjectedSession],
    *,
    routine_map: Sequence[MappedRoutine],
    folders: Collection[FolderRole],
    sessions_in_force: Collection[str],
    templates: Mapping[str, TemplateFacts],
) -> HevyActions:
    """One routine per projected session: its linked routine, else the oldest spare, else a new
    one (ADR 0011, "Routines and folders")."""
    linked = {row.session_id: row for row in routine_map if row.status in LINKED}
    updates = tuple(
        RoutineAction(s.session_id, linked[s.session_id].routine_id)
        for s in projected
        if s.session_id in linked
    )
    spares = iter(spare_routines(routine_map))
    creates = tuple(
        RoutineAction(s.session_id, next(spares, None))
        for s in projected
        if s.session_id not in linked
    )
    retires = tuple(
        RoutineAction(row.session_id, row.routine_id)
        for row in linked.values()
        if row.session_id not in sessions_in_force
    )
    needed: list[FolderRole] = []
    if any(not s.standing for s in projected):
        needed.append("program")
    if any(s.standing for s in projected):
        needed.append("standing")
    if retires:
        needed.append("retired")
    return HevyActions(
        folders=tuple(ENGINE_FOLDER_TITLES[role] for role in needed if role not in folders),
        updates=updates,
        creates=creates,
        retires=retires,
        templates=_templates(projected, templates),
    )


def spare_routines(routine_map: Sequence[MappedRoutine]) -> tuple[str, ...]:
    """Retired routines no other session holds, oldest retire first."""
    held = {row.routine_id for row in routine_map if row.status != "retired"}
    retired = sorted(
        (row for row in routine_map if row.status == "retired" and row.routine_id not in held),
        key=lambda row: (row.written_at, row.routine_id),
    )
    return tuple(dict.fromkeys(row.routine_id for row in retired))


def projected_sessions(sessions: Sequence[SessionPrescription]) -> tuple[ProjectedSession, ...]:
    """A push projects only the week's planned sessions that carry a line, one routine per
    session however many days it is planned on."""
    found: dict[str, ProjectedSession] = {}
    for prescribed in sessions:
        if not prescribed.lines:
            continue
        session = prescribed.session
        known = found.get(session.session_id)
        exercises = (
            *(known.exercises if known else ()),
            *(line.exercise_id for line in prescribed.lines),
        )
        found[session.session_id] = ProjectedSession(
            session.session_id, _standing(session), tuple(dict.fromkeys(exercises))
        )
    return tuple(found.values())


def _standing(session: PlannedSession) -> bool:
    """Standing, daily and rehab sessions live in the Standing folder."""
    return session.cadence in STANDING_CADENCES or session.kind == "rehab"


def _templates(
    projected: Sequence[ProjectedSession], templates: Mapping[str, TemplateFacts]
) -> tuple[TemplateCreate, ...]:
    found: dict[str, TemplateCreate] = {}
    for session in projected:
        for exercise_id in session.exercises:
            facts = templates.get(exercise_id)
            if facts is not None and facts.to_create:
                title = str(facts.columns["hevy_title"])
                found.setdefault(exercise_id, TemplateCreate(exercise_id, title))
    return tuple(found.values())


def _routine(action: RoutineAction) -> dict[str, object]:
    return {"session": action.session_id, "routine": action.routine_id}
