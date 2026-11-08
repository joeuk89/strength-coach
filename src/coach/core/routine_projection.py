"""A session's Hevy routine as the plan projects it, and the diff of a read-back against it
(ADR 0011, "Push"; docs/spec/parity.md, the routine body and note rules)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from coach.core.config import Units
from coach.core.exercise_ladder import rung_line
from coach.core.mirror import Routine, RoutineSet
from coach.core.program.form import Line

type Json = dict[str, object]
type DriftClass = Literal["structural", "load"]

WEIGHT_TOLERANCE_KG = 0.001
RETIRED_PREFIX = "(unused) "


@dataclass(frozen=True)
class FrozenLine:
    """One `prescription` row of a session: its exercise, frozen set groups and steps."""

    exercise_id: str
    set_groups: Sequence[Mapping[str, object]]
    steps: Sequence[Mapping[str, object]] = ()

    @property
    def authored_exercise(self) -> str:
        """The exercise the version authored, before any swap."""
        for step in self.steps:
            if step.get("cause") == "swap_exercise":
                return str(step["from"])
        return self.exercise_id


@dataclass(frozen=True)
class SessionRoutine:
    """`names` are the library's exercise names, for the next rung a ladder line's note names."""

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


def _authored(lines: Sequence[Line]) -> dict[str, _Authored]:
    """Every authored line keyed on its exercise, and a ladder line on each rung's exercise too,
    since the frozen row names the rung the week prescribed."""
    found: dict[str, _Authored] = {}
    for position, line in enumerate(lines):
        found[line.exercise] = _Authored(position, line)
        ladder = line.ladder
        if ladder is None:
            continue
        for index, rung in enumerate(ladder.rungs, start=1):
            following = ladder.rungs[index].exercise if index < len(ladder.rungs) else None
            found[rung.exercise] = _Authored(position, rung_line(line, ladder, index), following)
    return found


def next_rung_names(lines: Sequence[Line], names: Mapping[str, str]) -> dict[str, str]:
    """The next rung's display name, keyed on each authored exercise that has one. `names` are the
    library's exercise names; an exercise missing from them shows its id."""
    return {
        exercise: names.get(found.next_rung, found.next_rung)
        for exercise, found in _authored(lines).items()
        if found.next_rung is not None
    }


def project_routine(session: SessionRoutine, template_ids: Mapping[str, str], units: Units) -> Json:
    """The routine body: no null keys and no routine-level note, since Hevy drops it on PUT."""
    authored = _authored(session.authored)
    following = next_rung_names(session.authored, session.names)
    last = len(session.authored)
    lines = sorted(
        session.lines,
        key=lambda f: a.position if (a := authored.get(f.authored_exercise)) else last,
    )
    supersets: dict[str, int] = {}
    exercises: list[Json] = []
    for position, frozen in enumerate(lines):
        found = authored.get(frozen.authored_exercise)
        line = None if found is None else found.line
        notes = _notes(frozen, line, units)
        next_rung = following.get(frozen.authored_exercise)
        if next_rung is not None:
            notes.append(f"Next: {next_rung}")
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
    working = [g for g in groups if g.get("type") != "warm_up"]
    target = " + ".join(_shape(g) for g in working) or "no working set"
    loads = [float(str(g["load"])) for g in working if g.get("load") is not None]
    if loads:
        target += f" at {max(loads):g} {units}"
    rpes = {g.get("rpe") for g in working} - {None}
    if len(rpes) == 1:
        target += f" @{float(cast(float, rpes.pop())):g}"
    if not loads and any(g.get("reps") is not None or g.get("range") for g in working):
        target += ", choose the load"
    return target


def _shape(group: Mapping[str, object]) -> str:
    count = group["count"]
    reps = group.get("reps")
    rep_range = group.get("range")
    if isinstance(rep_range, list):
        low, high = cast(list[int], rep_range)
        return f"{count}×{low}–{high}"
    if isinstance(reps, str):
        shape = reps if count == 1 else f"{count}×{reps}"
        cap = group.get("rpe_cap")
        return shape if cap is None else f"{shape} (stop at RPE {float(cast(float, cap)):g})"
    if reps is not None:
        return f"{count}×{reps}"
    return f"{count}×{group.get('duration_s')} s"


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
