"""The closed weeks and their Blocks as a view of the store (docs/spec/week.md; ADR 0018)."""

import datetime
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.closed_week.block import Block, blocks
from coach.core.closed_week.close import WeekFacts, close_week
from coach.core.closed_week.dose import MuscleMap
from coach.core.closed_week.kind import is_return_week
from coach.core.closed_week.match import PlannedRef, WeekWorkout, workout_class
from coach.core.closed_week.sessions import PlannedWork, TargetSet
from coach.core.closed_week.week import ClosedWeek
from coach.core.config import Units
from coach.core.exposure import Annotation, LoggedWorkout, resolve
from coach.core.muscles import read_muscles
from coach.core.planned_week import DAYS_IN_WEEK, choose_sessions, planned_sessions, week_monday
from coach.core.prescription import PlanOverride, StatusSpan
from coach.core.program.form import ProgramForm
from coach.core.ref import Ref
from coach.store import (
    annotations,
    check_ins,
    decisions,
    exercises,
    niggles,
    programs,
    readings,
    routine_map,
    week_plans,
    workouts,
)
from coach.store.connection import Connection
from coach.store.rows import Row

WEEK_OVERRIDES = ("light_week", "minimum_week", "one_off_week")


@dataclass(frozen=True)
class ClosedWeeks:
    weeks: tuple[ClosedWeek, ...] = ()
    blocks: tuple[Block, ...] = ()

    @property
    def open_block(self) -> Block | None:
        return self.blocks[-1] if self.blocks else None


def closed_weeks(conn: Connection, units: Units = "kg") -> ClosedWeeks:
    redesigns = [datetime.date.fromisoformat(d) for d in programs.redesigns(conn)]
    if not redesigns:
        return ClosedWeeks()
    log = _Log(conn, units)
    weeks = tuple(close_week(log.facts(monday)) for monday in _closed_mondays(conn, redesigns[0]))
    return ClosedWeeks(weeks, blocks([(w.monday, w.kind) for w in weeks], redesigns))


def status_spans(conn: Connection) -> tuple[StatusSpan, ...]:
    return tuple(
        StatusSpan(
            str(row["kind"]),
            datetime.date.fromisoformat(str(row["from_date"])),
            None if row["to_date"] is None else datetime.date.fromisoformat(str(row["to_date"])),
        )
        for row in readings.live(conn, "status_span")
    )


def muscle_map(conn: Connection) -> MuscleMap:
    return {str(row["id"]): read_muscles(row["muscles"]) or {} for row in exercises.every(conn)}


def parked_sessions(conn: Connection, monday: datetime.date) -> frozenset[str]:
    """A park supersedes the resume before it on the same session, and the other way round."""
    return frozenset(
        str(row["session_id"])
        for row in decisions.in_force(conn, monday.isoformat())
        if row["kind"] == "park_session"
    )


def _closed_mondays(conn: Connection, first: datetime.date) -> list[datetime.date]:
    windows = check_ins.current_windows(conn)
    if not windows:
        return []
    last = max(end for _, end in windows)
    found: list[datetime.date] = []
    monday = week_monday(first)
    while monday <= last:
        sunday = monday + datetime.timedelta(days=DAYS_IN_WEEK - 1)
        if any(start <= sunday <= end for start, end in windows):
            found.append(monday)
        monday += datetime.timedelta(weeks=1)
    return found


class _Log:
    """What every closed week reads, loaded once."""

    def __init__(self, conn: Connection, units: Units) -> None:
        self.conn = conn
        library = exercises.library(conn)
        live = annotations.live(conn)
        current = workouts.current_workouts(conn)
        exposures = resolve(
            (LoggedWorkout(v.id, _day(v.date), v.sets) for v in current), library, live, units
        )
        self.workouts = tuple(
            WeekWorkout(
                v.id,
                _day(v.date),
                tuple(e for e in exposures if e.workout_id == v.id),
                v.routine_id,
                _started(v.raw),
                workout_class(v.sets, library),
                v.minutes,
            )
            for v in current
        )
        self.lifting_dates = [w.date for w in self.workouts if w.kind == "lifting"]
        self.claims = _claims(live, self.workouts, workouts.sessions_of_current(conn))
        self.trained_unlogged = _planned_refs(live, "trained_unlogged")
        self.cancelled = _planned_refs(live, "cancelled")
        self.spans = status_spans(conn)
        self.routines = routine_map.mapped(conn)
        self.rehab = niggles.open_rehab_sessions(conn)
        self.muscles = muscle_map(conn)

    def facts(self, monday: datetime.date) -> WeekFacts:
        sunday = monday + datetime.timedelta(days=DAYS_IN_WEEK - 1)
        plan = week_plans.in_force(self.conn, monday.isoformat())
        at = str(plan["approved_at"]) if plan else f"{sunday.isoformat()}T23:59:59"
        version = programs.in_force_at(self.conn, at)
        form = version.form if version else None
        overrides = week_plans.stored_overrides(self.conn, str(plan["id"])) if plan else ()
        return WeekFacts(
            monday,
            planned=self._planned(plan, form, overrides, monday) if plan and form else (),
            workouts=tuple(w for w in self.workouts if monday <= w.date <= sunday),
            routines=self.routines,
            claims=self.claims,
            trained_unlogged=self.trained_unlogged,
            cancelled=self.cancelled,
            spans=self.spans,
            carried=frozenset(o.kind for o in overrides if o.kind in WEEK_OVERRIDES),
            returned=is_return_week(monday, self.lifting_dates),
            muscles=self.muscles,
            estimated={s.id: s.estimated_sets for s in form.sessions if s.estimated_sets}
            if form
            else {},
            dose_target=form.dose.per_muscle if form and form.dose else None,
        )

    def _planned(
        self,
        plan: Row,
        form: ProgramForm,
        overrides: Sequence[PlanOverride],
        monday: datetime.date,
    ) -> tuple[PlannedWork, ...]:
        """A drop stays in the week as a Miss, so the sessions derive without it."""
        plan_id = str(plan["id"])
        dropped = {o.session_id for o in overrides if o.kind == "drop_session"}
        held = {(o.session_id, o.exercise_id) for o in overrides if o.kind == "hold"}
        sessions = choose_sessions(
            planned_sessions(
                form,
                position=str(plan["position"]),
                monday=monday,
                rehab=self.rehab,
                parked=parked_sessions(self.conn, monday),
            ),
            [o for o in overrides if o.kind != "drop_session"],
            form=form,
            monday=monday,
            rehab=self.rehab,
        )
        hold_lines = held | {
            (s.session_id, line.exercise)
            for s in sessions
            for line in s.lines
            if line.scheme.name == "hold"
        }
        targets = _targets(week_plans.prescriptions(self.conn, plan_id), hold_lines)
        return tuple(
            PlannedWork(
                s,
                targets.get((s.date, s.session_id), {}),
                dropped=s.session_id in dropped,
            )
            for s in sessions
        )


def _targets(
    rows: Sequence[Row], hold_lines: set[tuple[str | None, str | None]]
) -> dict[PlannedRef, dict[str, tuple[TargetSet, ...]]]:
    found: dict[PlannedRef, dict[str, tuple[TargetSet, ...]]] = {}
    for row in rows:
        session_id, exercise_id = str(row["session_id"]), str(row["exercise_id"])
        if (session_id, exercise_id) in hold_lines:
            continue
        groups = cast(list[dict[str, object]], row["set_groups"])
        sets = tuple(
            TargetSet(_bottom(group), _number(group.get("rpe")))
            for group in groups
            if group.get("type") == "working"
            for _ in range(int(cast(int, group.get("count", 1))))
        )
        if sets:
            found.setdefault((_day(str(row["date"])), session_id), {})[exercise_id] = sets
    return found


def _claims(
    live: Sequence[Annotation], logged: Sequence[WeekWorkout], manual: Mapping[str, str]
) -> dict[str, PlannedRef]:
    dates = {w.id: w.date for w in logged}
    found: dict[str, PlannedRef] = {
        workout_id: (dates[workout_id], session_id)
        for workout_id, session_id in manual.items()
        if workout_id in dates
    }
    for annotation in live:
        planned = annotation.params.get("planned_session")
        if annotation.kind == "match" and isinstance(planned, str):
            workout_id = Ref.parse(annotation.target).id.partition("/")[0]
            found[workout_id] = _planned_ref(planned)
    return found


def _planned_refs(live: Sequence[Annotation], kind: str) -> frozenset[PlannedRef]:
    return frozenset(_planned_ref(a.target) for a in live if a.kind == kind)


def _planned_ref(text: str) -> PlannedRef:
    day, _, session_id = Ref.parse(text).id.partition("/")
    return (_day(day), session_id)


def _bottom(group: Mapping[str, object]) -> int | None:
    reps = group.get("range") or group.get("reps")
    if isinstance(reps, list):
        return int(cast(list[int], reps)[0])
    return reps if isinstance(reps, int) else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _started(raw: str | None) -> str:
    """Hevy's start time orders two workouts on one day; a manual workout has none."""
    payload: object = json.loads(raw) if raw else {}
    started = (
        cast(dict[str, object], payload).get("start_time") if isinstance(payload, dict) else None
    )
    return started if isinstance(started, str) else ""


def _day(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)
