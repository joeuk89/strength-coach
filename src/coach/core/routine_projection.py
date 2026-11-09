"""A session's Hevy routine as the plan projects it, and the diff of a read-back against it
(ADR 0011, "Push"; docs/spec/parity.md, the routine body and note rules)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from coach.core.config import Units
from coach.core.exercise_ladder import rung_label, rung_line
from coach.core.mirror import Routine, RoutineSet
from coach.core.note_dose import working_groups, working_rpe, working_shape
from coach.core.prescription import RungNaming
from coach.core.program.form import Line

type Json = dict[str, object]
type DriftClass = Literal["structural", "load"]
type RungKey = tuple[str, int | None]

WEIGHT_TOLERANCE_KG = 0.001
RETIRED_PREFIX = "(unused) "


@dataclass(frozen=True)
class FrozenLine:
    """One `prescription` row of a session: its exercise, frozen set groups and steps, and on a
    ladder the rung its week prescribed."""

    exercise_id: str
    set_groups: Sequence[Mapping[str, object]]
    steps: Sequence[Mapping[str, object]] = ()
    rung: int | None = None


def authored_exercise(exercise_id: str, steps: Sequence[Mapping[str, object]]) -> str:
    """The exercise the version authored, before any swap."""
    for step in steps:
        if step.get("cause") == "swap_exercise":
            return str(step["from"])
    return exercise_id


def _origin(frozen: FrozenLine) -> RungKey:
    return authored_exercise(frozen.exercise_id, frozen.steps), frozen.rung


@dataclass(frozen=True)
class SessionRoutine:
    """`names` are the library's exercise names, for the next rung's label on a ladder line's
    note."""

    title: str
    folder_id: str
    week_line: str
    authored: Sequence[Line]
    lines: Sequence[FrozenLine]
    names: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class _Authored:
    """The authored line a frozen line projects from: on a ladder, the line as the frozen rung
    prescribes it, with the next rung's exercise."""

    position: int
    line: Line
    next_rung: str | None = None


def _authored(lines: Sequence[Line], naming: RungNaming) -> dict[RungKey, _Authored]:
    """Every authored line keyed on its exercise and no rung, and a ladder line on each rung's
    exercise and index too. A row frozen before rungs were recorded has no rung, and finds its
    ladder rung by exercise: adopt then refused two rungs on one exercise."""
    found: dict[RungKey, _Authored] = {}
    for position, line in enumerate(lines):
        found[line.exercise, None] = _Authored(position, line)
        ladder = line.ladder
        if ladder is None:
            continue
        for index, rung in enumerate(ladder.rungs, start=1):
            following = (
                rung_label(line, ladder, index + 1, standing=index, naming=naming)
                if index < len(ladder.rungs)
                else None
            )
            shaped = _Authored(position, rung_line(line, ladder, index), following)
            found[rung.exercise, index] = shaped
            found[rung.exercise, None] = shaped
    return found


def next_rung_labels(lines: Sequence[Line], naming: RungNaming) -> dict[RungKey, str]:
    """The next rung's label, keyed on each authored exercise and rung that has one. A frozen row
    records only the rung its week prescribed, so that rung is the label's standing rung."""
    return {
        key: found.next_rung
        for key, found in _authored(lines, naming).items()
        if found.next_rung is not None
    }


def project_routine(session: SessionRoutine, template_ids: Mapping[str, str], units: Units) -> Json:
    """The routine body: no null keys and no routine-level note, since Hevy drops it on PUT."""
    authored = _authored(session.authored, RungNaming(units, session.names))
    last = len(session.authored)
    lines = sorted(
        session.lines,
        key=lambda f: a.position if (a := authored.get(_origin(f))) else last,
    )
    supersets: dict[str, int] = {}
    exercises: list[Json] = []
    for position, frozen in enumerate(lines):
        found = authored.get(_origin(frozen))
        line = None if found is None else found.line
        notes = _notes(frozen, line, units)
        if found is not None and found.next_rung is not None:
            notes.append(f"Next: {found.next_rung}")
        if position == 0:
            notes = [session.week_line, *notes]
        exercise: Json = {
            "exercise_template_id": template_ids[frozen.exercise_id],
            "notes": "\n".join(notes),
            "sets": [s for group in frozen.set_groups for s in _sets(group)],
        }
        if line is not None:
            exercise["rest_seconds"] = line.rest_s
            if line.superset is not None:
                exercise["superset_id"] = supersets.setdefault(line.superset, len(supersets))
        exercises.append(exercise)
    return {
        "title": session.title,
        "folder_id": _hevy_folder_id(session.folder_id),
        "exercises": exercises,
    }


def retired_routine(live: Routine, folder_id: str) -> Json:
    """The spare: the routine under `(unused) <title>` in the Retired folder, exercises kept."""
    title = live.title if live.title.startswith(RETIRED_PREFIX) else RETIRED_PREFIX + live.title
    exercises: list[Json] = []
    for exercise in live.exercises:
        kept: Json = {
            "exercise_template_id": exercise.hevy_template_id,
            "rest_seconds": exercise.rest_s,
            "notes": exercise.notes,
            "superset_id": exercise.superset_id,
            "sets": [_kept_set(s) for s in exercise.sets],
        }
        exercises.append({k: v for k, v in kept.items() if v is not None})
    return {"title": title, "folder_id": _hevy_folder_id(folder_id), "exercises": exercises}


def routine_diff(body: Mapping[str, object], routine: Routine) -> tuple[str, ...]:
    """What the read-back changed, by position: template id, set type, reps or range, duration,
    `weight_kg` within 0.001, rest, exercise notes, title and folder."""
    found: list[str] = []
    if body.get("title") != routine.title:
        found.append("title")
    if _text(body.get("folder_id")) != routine.folder_id:
        found.append("folder")
    sent = cast(Sequence[Mapping[str, object]], body.get("exercises") or [])
    if len(sent) != len(routine.exercises):
        return (*found, "exercise count")
    for n, (want, got) in enumerate(zip(sent, routine.exercises, strict=True), start=1):
        where = f"exercise {n}"
        if want.get("exercise_template_id") != got.hevy_template_id:
            found.append(f"{where} template")
        if want.get("rest_seconds") != got.rest_s:
            found.append(f"{where} rest")
        if (want.get("notes") or None) != got.notes:
            found.append(f"{where} notes")
        sets = cast(Sequence[Mapping[str, object]], want.get("sets") or [])
        if len(sets) != len(got.sets):
            found.append(f"{where} set count")
            continue
        for m, (set_sent, set_got) in enumerate(zip(sets, got.sets, strict=True), start=1):
            found += [f"{where} set {m} {field}" for field in _set_diff(set_sent, set_got)]
    return tuple(found)


def drift_class(diff: Sequence[str]) -> DriftClass:
    """An app edit that only moved weights is a load edit; anything else is structural."""
    return "load" if all(d.endswith("weight_kg") for d in diff) else "structural"


def _hevy_folder_id(folder_id: str) -> int | str:
    """Hevy numbers its folders; the mirror keeps the id as text."""
    return int(folder_id) if folder_id.isdigit() else folder_id


def _notes(frozen: FrozenLine, line: Line | None, units: Units) -> list[str]:
    notes = [f"Target: {_target(frozen.set_groups, units)}"]
    if line is not None and line.cues:
        notes.append(f"Cues: {line.cues}")
    return notes


def _target(groups: Sequence[Mapping[str, object]], units: Units) -> str:
    """`2×5 + 5+ (stop at RPE 9) at 225 lb @8`; a line with no working load says
    `choose the load` once."""
    working = working_groups(groups)
    target = working_shape(working)
    loads = [float(str(g["load"])) for g in working if g.get("load") is not None]
    if loads:
        target += f" at {max(loads):g} {units}"
    target += working_rpe(working)
    if not loads and any(g.get("reps") is not None or g.get("range") for g in working):
        target += ", choose the load"
    return target


def _sets(group: Mapping[str, object]) -> list[Json]:
    one: Json = {"type": "warmup" if group.get("type") == "warm_up" else "normal"}
    if group.get("load_kg") is not None:
        one["weight_kg"] = group["load_kg"]
    rep_range = group.get("range")
    if isinstance(rep_range, list):
        low, high = cast(list[int], rep_range)
        one["rep_range"] = {"start": low, "end": high}
    elif group.get("reps") is not None:
        one["reps"] = _floor(cast(int | str, group["reps"]))
    if group.get("duration_s") is not None:
        one["duration_seconds"] = group["duration_s"]
    return [dict(one) for _ in range(cast(int, group["count"]))]


def _floor(reps: int | str) -> int:
    """A rep-out such as `5+` goes to Hevy as its floor; the note carries the `+`."""
    return int(reps.rstrip("+")) if isinstance(reps, str) else reps


def _kept_set(kept: RoutineSet) -> Json:
    one: Json = {
        "type": kept.set_type,
        "weight_kg": kept.weight_kg,
        "reps": kept.reps,
        "duration_seconds": kept.duration_s,
        "distance_meters": kept.distance_m,
    }
    if kept.rep_range is not None:
        one["rep_range"] = {"start": kept.rep_range[0], "end": kept.rep_range[1]}
    return {k: v for k, v in one.items() if v is not None}


def _set_diff(sent: Mapping[str, object], got: RoutineSet) -> list[str]:
    found: list[str] = []
    if sent.get("type") != got.set_type:
        found.append("type")
    if sent.get("reps") != got.reps:
        found.append("reps")
    span = cast(Mapping[str, int] | None, sent.get("rep_range"))
    if (None if span is None else (span["start"], span["end"])) != got.rep_range:
        found.append("range")
    if sent.get("duration_seconds") != got.duration_s:
        found.append("duration")
    weight = cast(float | None, sent.get("weight_kg"))
    if (weight is None) != (got.weight_kg is None) or (
        weight is not None
        and got.weight_kg is not None
        and abs(weight - got.weight_kg) > WEIGHT_TOLERANCE_KG
    ):
        found.append("weight_kg")
    return found


def _text(value: object) -> str | None:
    return None if value is None else str(value)
