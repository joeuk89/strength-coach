"""A session's Hevy routine as the plan projects it, and the diff of a read-back against it
(ADR 0011, "Push"; docs/spec/parity.md, the routine body and note rules)."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from coach.core.config import Units
from coach.core.exercise_ladder import rung_label, rung_line
from coach.core.exposure import LibraryEntry
from coach.core.load import PRECISION, Load, LoadMode
from coach.core.mirror import Routine, RoutineExercise, RoutineSet
from coach.core.note_dose import working_rpe, working_shape
from coach.core.prescription import RungNaming, stepped_back_to
from coach.core.program.form import Line
from coach.core.units import from_kg

type Json = dict[str, object]
type DriftClass = Literal["structural", "load"]
type RungKey = tuple[str, int | None]

WEIGHT_TOLERANCE_KG = 0.001
RETIRED_PREFIX = "(unused) "
NEXT_LINE_PREFIX = "Next: "


@dataclass(frozen=True)
class FrozenLine:
    """One `prescription` row of a session: its exercise, frozen set groups and steps, and on a
    ladder the rung its week prescribed."""

    exercise_id: str
    set_groups: Sequence[Mapping[str, object]]
    steps: Sequence[Mapping[str, object]] = ()
    rung: int | None = None


def in_routine(set_groups: Sequence[object]) -> bool:
    """Hevy drops an exercise with no sets, so a line frozen with none, such as one an `avoid`
    constraint drops, is left out of its routine."""
    return bool(set_groups)


def row_in_routine(row: Mapping[str, object]) -> bool:
    return in_routine(cast(Sequence[object], row["set_groups"]))


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
class RungLabels:
    """A frozen rung's own label and the next rung's, if any. A frozen row records only the rung
    its week prescribed, so that rung is the standing rung of both."""

    own: str
    next: str | None


@dataclass(frozen=True)
class _Authored:
    """The authored line a frozen line projects from: on a ladder, the line as the frozen rung
    prescribes it, with its labels."""

    position: int
    line: Line
    labels: RungLabels | None = None


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
            labels = RungLabels(
                own=rung_label(line, ladder, index, standing=index, naming=naming),
                next=(
                    rung_label(line, ladder, index + 1, standing=index, naming=naming)
                    if index < len(ladder.rungs)
                    else None
                ),
            )
            shaped = _Authored(position, rung_line(line, ladder, index), labels)
            found[rung.exercise, index] = shaped
            found[rung.exercise, None] = shaped
    return found


def week_labels(labels: RungLabels, steps: Sequence[Mapping[str, object]]) -> RungLabels:
    """A stepped-back week offers no climb, since the line returns to its standing rung next, and
    names its rung by index alone, since the band cut the dose the label would print."""
    to = stepped_back_to(steps)
    return labels if to is None else RungLabels(own=f"rung {to}", next=None)


def rung_labels(lines: Sequence[Line], naming: RungNaming) -> dict[RungKey, RungLabels]:
    """The labels of every ladder rung, keyed on the authored exercise and rung."""
    return {
        key: found.labels
        for key, found in _authored(lines, naming).items()
        if found.labels is not None
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
        if found is not None and found.labels is not None:
            notes += _rung_notes(found.labels, frozen.steps)
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


type ChangeField = Literal[
    "title",
    "folder",
    "removed",
    "added",
    "exercise",
    "rest",
    "notes",
    "set_count",
    "type",
    "reps",
    "range",
    "duration",
    "load",
]

_SUFFIXES: Mapping[str, str] = {"rest": " s", "duration": " s"}


@dataclass(frozen=True)
class RoutineChange:
    """One difference between a projected routine and the one Hevy holds. `exercise_id` names
    the planned exercise, or for an added one the exercise or template Hevy holds; a load is in
    athlete units, per hand under `per_hand_x2`."""

    field: ChangeField
    exercise_id: str | None = None
    set: int | None = None
    planned: object = None
    found: object = None
    units: Units | None = None

    def to_json(self) -> Json:
        return {
            "field": self.field,
            "exercise_id": self.exercise_id,
            "set": self.set,
            "planned": self.planned,
            "found": self.found,
        }

    @property
    def text(self) -> str:
        """`bb_back_squat set 2 load 125 → 135 lb`, `db_curl removed`."""
        if self.field == "added" and self.exercise_id is None:
            return f"template {self.found} added"
        if self.field in ("removed", "added"):
            return f"{self.exercise_id} {self.field}"
        if self.field == "exercise":
            return f"{self.exercise_id} swapped for {self.found}"
        if self.field == "notes":
            return f"{self.exercise_id} notes"
        if self.field in ("title", "folder"):
            return f"{self.field} {_shown(self.planned)} → {_shown(self.found)}"
        where = self.exercise_id if self.set is None else f"{self.exercise_id} set {self.set}"
        suffix = f" {self.units}" if self.field == "load" else _SUFFIXES.get(self.field, "")
        label = self.field.replace("_", " ")
        return f"{where} {label} {_shown(self.planned)} → {_shown(self.found)}{suffix}"


def _shown(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return "-".join(str(v) for v in cast(list[object], value))
    return str(value)


def routine_diff(
    body: Mapping[str, object],
    routine: Routine,
    library: Mapping[str, LibraryEntry],
    units: Units,
) -> tuple[RoutineChange, ...]:
    """What the read-back changed, by position: template, set type, reps or range, duration,
    `weight_kg` within 0.001, rest, exercise notes, title and folder. `library` names each
    Exercise by the template it carries."""
    return _Differ(library, units, lambda note: note).diff(body, routine)


def drift_diff(
    body: Mapping[str, object],
    routine: Routine,
    library: Mapping[str, LibraryEntry],
    units: Units,
) -> tuple[RoutineChange, ...]:
    """What an app edit changed: `routine_diff`, setting aside each note's `Next:` line on both
    sides, since the engine derives that line and its wording moves between releases."""
    return _Differ(library, units, _without_next_line).diff(body, routine)


def diff_text(changes: Sequence[RoutineChange]) -> tuple[str, ...]:
    return tuple(c.text for c in changes)


@dataclass(frozen=True)
class _Differ:
    library: Mapping[str, LibraryEntry]
    units: Units
    compared_note: Callable[[str | None], str | None]

    def diff(self, body: Mapping[str, object], routine: Routine) -> tuple[RoutineChange, ...]:
        found: list[RoutineChange] = []
        if body.get("title") != routine.title:
            found.append(RoutineChange("title", planned=body.get("title"), found=routine.title))
        folder = _text(body.get("folder_id"))
        if folder != routine.folder_id:
            found.append(RoutineChange("folder", planned=folder, found=routine.folder_id))
        sent = cast(Sequence[Mapping[str, object]], body.get("exercises") or [])
        if len(sent) != len(routine.exercises):
            return (*found, *self._count(sent, routine))
        for want, got in zip(sent, routine.exercises, strict=True):
            found += self._exercise(want, got)
        return tuple(found)

    def _named(self, template_id: object) -> str:
        """The Exercise carrying the template, or the template id when none does."""
        entry = self.library.get(str(template_id))
        return str(template_id) if entry is None else entry.exercise_id

    def _count(self, sent: Sequence[Mapping[str, object]], routine: Routine) -> list[RoutineChange]:
        planned = Counter(self._named(e.get("exercise_template_id")) for e in sent)
        held = Counter(self._named(e.hevy_template_id) for e in routine.exercises)
        mapped = {entry.exercise_id for entry in self.library.values()}
        return [
            *(RoutineChange("removed", name, planned=name) for name in (planned - held).elements()),
            *(
                RoutineChange("added", name if name in mapped else None, found=name)
                for name in (held - planned).elements()
            ),
        ]

    def _exercise(self, want: Mapping[str, object], got: RoutineExercise) -> list[RoutineChange]:
        template = want.get("exercise_template_id")
        name = self._named(template)
        if template != got.hevy_template_id:
            held = self._named(got.hevy_template_id)
            return [RoutineChange("exercise", name, planned=name, found=held)]
        found: list[RoutineChange] = []
        if want.get("rest_seconds") != got.rest_s:
            found.append(
                RoutineChange("rest", name, planned=want.get("rest_seconds"), found=got.rest_s)
            )
        sent_note = cast(str | None, want.get("notes")) or None
        if self.compared_note(sent_note) != self.compared_note(got.notes):
            found.append(RoutineChange("notes", name, planned=sent_note, found=got.notes))
        sets = cast(Sequence[Mapping[str, object]], want.get("sets") or [])
        if len(sets) != len(got.sets):
            found.append(RoutineChange("set_count", name, planned=len(sets), found=len(got.sets)))
            return found
        entry = self.library.get(str(template))
        mode = "total" if entry is None else entry.load_mode
        for m, (set_sent, set_got) in enumerate(zip(sets, got.sets, strict=True), start=1):
            found += [
                RoutineChange(field, name, m, planned, held, self.units)
                for field, planned, held in _set_diff(set_sent, set_got, mode, self.units)
            ]
        return found


def drift_class(changes: Sequence[RoutineChange]) -> DriftClass:
    """An app edit that only moved weights is a load edit; anything else is structural."""
    return "load" if all(c.field == "load" for c in changes) else "structural"


def _without_next_line(note: str | None) -> str | None:
    if note is None:
        return None
    kept = [line for line in note.split("\n") if not line.startswith(NEXT_LINE_PREFIX)]
    return "\n".join(kept) or None


def _hevy_folder_id(folder_id: str) -> int | str:
    """Hevy numbers its folders; the mirror keeps the id as text."""
    return int(folder_id) if folder_id.isdigit() else folder_id


def _notes(frozen: FrozenLine, line: Line | None, units: Units) -> list[str]:
    notes = [f"Target: {_target(frozen.set_groups, units)}"]
    if line is not None and line.cues:
        notes.append(f"Cues: {line.cues}")
    return notes


def _rung_notes(labels: RungLabels, steps: Sequence[Mapping[str, object]]) -> list[str]:
    to = stepped_back_to(steps)
    if to is not None:
        return [f"This week: rung {to}"]
    return [] if labels.next is None else [f"{NEXT_LINE_PREFIX}{labels.next}"]


def _target(groups: Sequence[Mapping[str, object]], units: Units) -> str:
    """`2×5 + 5+ (stop at RPE 9) at 225 lb @8`; a line with no working load says
    `choose the load` once."""
    working = [g for g in groups if g.get("type") != "warm_up"]
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


type _SetChange = tuple[ChangeField, object, object]


def _set_diff(
    sent: Mapping[str, object], got: RoutineSet, mode: LoadMode, units: Units
) -> list[_SetChange]:
    found: list[_SetChange] = []
    if sent.get("type") != got.set_type:
        found.append(("type", sent.get("type"), got.set_type))
    if sent.get("reps") != got.reps:
        found.append(("reps", sent.get("reps"), got.reps))
    span = cast(Mapping[str, int] | None, sent.get("rep_range"))
    planned_range = None if span is None else (span["start"], span["end"])
    if planned_range != got.rep_range:
        found.append(("range", _listed(planned_range), _listed(got.rep_range)))
    if sent.get("duration_seconds") != got.duration_s:
        found.append(("duration", sent.get("duration_seconds"), got.duration_s))
    weight = cast(float | None, sent.get("weight_kg"))
    if (weight is None) != (got.weight_kg is None) or (
        weight is not None
        and got.weight_kg is not None
        and abs(weight - got.weight_kg) > WEIGHT_TOLERANCE_KG
    ):
        found.append(
            ("load", _athlete_load(weight, mode, units), _athlete_load(got.weight_kg, mode, units))
        )
    return found


def _listed(span: tuple[int, int] | None) -> list[int] | None:
    return None if span is None else list(span)


def _athlete_load(kg: float | None, mode: LoadMode, units: Units) -> float | None:
    if kg is None:
        return None
    return round(Load(from_kg(kg, units), "total").as_mode(mode).amount, PRECISION)


def _text(value: object) -> str | None:
    return None if value is None else str(value)
