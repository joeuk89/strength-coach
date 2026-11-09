"""The violations `program adopt` raises on a form (docs/spec/program.md, "Violations")."""

import itertools
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from coach.core.closed_week.adherence import Adherence
from coach.core.config import WEEKDAYS, Weekday
from coach.core.exposure import Exposure
from coach.core.flag import Flag, FlagKey, Scope, raise_flag
from coach.core.goal import Goal
from coach.core.muscles import read_muscles
from coach.core.program.form import (
    LOAD_BEARING_MODES,
    RACK_MODES,
    Advance,
    ExerciseLadder,
    Line,
    Number,
    ProgramForm,
    Rung,
    SchemeRef,
    Session,
    SetGroup,
)
from coach.core.rack import Rack, on_rack, rows_beside
from coach.core.registries.flags import FLAGS
from coach.core.registries.hevy import HEVY_EQUIPMENT, HEVY_EXERCISE_TYPES, HEVY_MUSCLE_GROUPS
from coach.core.registries.program import LOAD_MODES, MUSCLES, PATTERNS
from coach.core.registries.registry import Registry, Term
from coach.core.registries.schemes import SCHEMES, Param, ParamType, Scheme

TEMPLATE_COLUMNS = ("hevy_title", "hevy_exercise_type", "hevy_equipment", "hevy_muscle_group")
TEMPLATE_REGISTRIES: Mapping[str, Registry[Term]] = {
    "hevy_exercise_type": HEVY_EXERCISE_TYPES,
    "hevy_equipment": HEVY_EQUIPMENT,
    "hevy_muscle_group": HEVY_MUSCLE_GROUPS,
}
NO_LOAD_MODES = ("bodyweight", "duration", "distance")
# Warnings raised once per case; acknowledging the version-wide key names the per-case keys.
PER_CASE_WARNINGS = {
    "dose_off_band": "dose target",
    "priority_lift_absent": "priority lift",
    "counted_variant_off_pattern": "counted variant",
}


@dataclass(frozen=True)
class _Loaded:
    """A line, or a rung after the first, as the start-load checks read it."""

    exercise_id: str
    exercise: Mapping[str, object]
    mode: str
    start_load: Number | None
    key_path: str
    needed: bool
    needed_because: str
    rung: int | None = None

    @property
    def rung_param(self) -> dict[str, object]:
        return {} if self.rung is None else {"rung": self.rung}

    @property
    def distinct(self) -> str:
        return "" if self.rung is None else f"rung {self.rung}"


@dataclass(frozen=True)
class OpenBlock:
    id: str
    hard_weeks: int


@dataclass(frozen=True)
class AdoptContext:
    """What the checks read beside the form, as values. `racks` maps each location in
    `coach.toml` to the rack of every equipment kind it supplies; `last_exposures` each exercise
    with an Exposure anywhere to its latest; `routines` each mapped session to its routine id;
    `signals` each exercise with an open cadence signal to that signal."""

    version_id: str
    library: Mapping[str, Mapping[str, object]]
    racks: Mapping[str, Mapping[str, Rack]]
    last_exposures: Mapping[str, Exposure] = field(default_factory=dict[str, Exposure])
    goal: Goal | None = None
    phase: str | None = None
    available_days: tuple[Weekday, ...] = WEEKDAYS
    hevy_on: bool = False
    previous: ProgramForm | None = None
    routines: Mapping[str, str] = field(default_factory=dict[str, str])
    open_block: OpenBlock | None = None
    adherence: Adherence | None = None
    raised_warnings: frozenset[str] = field(default_factory=frozenset[str])
    signals: Mapping[str, Flag] = field(default_factory=dict[str, Flag])


def violations(
    form: ProgramForm, context: AdoptContext, unknown_keys: Sequence[str] = ()
) -> tuple[Flag, ...]:
    check = _Checks(form, context, list(unknown_keys))
    check.version()
    check.exercises()
    for session in form.sessions:
        check.session(session)
    check.unknown_keys()
    check.acknowledgements()
    return check.flags()


class _Checks:
    def __init__(self, form: ProgramForm, context: AdoptContext, unknown: list[str]) -> None:
        self.form = form
        self.context = context
        self.unknown = unknown
        self.found: dict[str, Flag] = {}
        self.version_scope = Scope("version", version_id=context.version_id)

    def flags(self) -> tuple[Flag, ...]:
        return tuple(self.found.values())

    def raise_(
        self,
        code: str,
        scope: Scope,
        params: Mapping[str, object],
        message: str,
        *,
        distinct: str = "",
    ) -> None:
        flag = raise_flag(code, scope, params, message)
        self.found.setdefault(f"{flag.key}#{distinct}" if distinct else flag.key, flag)

    def version(self) -> None:
        form, context = self.form, self.context
        if form.location not in context.racks:
            self.raise_(
                "location_unknown",
                self.version_scope,
                {"location": form.location},
                f"location {form.location!r} has no [location.{form.location}] in coach.toml",
            )
        self._duplicate_ids()
        self._counted_variants()
        for week, day, session_id in form.schedule.slots():
            if form.session(session_id) is None:
                self.raise_(
                    "schedule_session_missing",
                    self.version_scope,
                    {"week": week, "weekday": day, "session_id": session_id},
                    f"schedule.{week}.{day} names {session_id!r}, which the version lacks",
                )
                break
        if context.goal is None:
            self.raise_("goal_missing", self.version_scope, {}, "no current Goal; run goal adopt")
        elif form.emphasis == "strength" and not context.goal.priority_lifts:
            self.raise_(
                "priority_lifts_required",
                self.version_scope,
                {"emphasis": form.emphasis},
                "a strength version needs a Goal with priority lifts",
            )

    def exercises(self) -> None:
        referenced = [
            exercise
            for session in self.form.sessions
            for line in session.lines
            for exercise in _exercises_of(line)
        ]
        counts = self.form.dose.counted().values() if self.form.dose else ()
        counted = [variant for variants in counts for variant in variants]
        for id_ in dict.fromkeys([*referenced, *counted, *self.form.exercises]):
            exercise = self._exercise(id_)
            if exercise is not None:
                self._exercise_names(id_, exercise)

    def _exercise_names(self, id_: str, exercise: Mapping[str, object]) -> None:
        scope = Scope("exercise", exercise_id=id_)
        pattern = exercise.get("pattern")
        if pattern is not None and pattern not in PATTERNS:
            self.raise_(
                "unknown_pattern",
                scope,
                {"pattern": pattern},
                f"{id_} has pattern {pattern!r}, which is no pattern; coach schema --registry "
                "patterns",
            )
        muscles = read_muscles(exercise.get("muscles"))
        named = [*muscles["primary"], *muscles["secondary"]] if muscles else []
        self._muscles(named, scope, f"{id_} names")

    def _muscles(self, names: Iterable[str], scope: Scope, where: str) -> None:
        unknown = next((name for name in names if name not in MUSCLES), None)
        if unknown is not None:
            self.raise_(
                "unknown_muscle",
                scope,
                {"muscle": unknown},
                f"{where} {unknown!r}, which is no muscle; coach schema --registry muscles",
            )

    def _duplicate_ids(self) -> None:
        slots: set[tuple[str, str, str]] = set()
        for week, day, session_id in self.form.schedule.slots():
            if (week, day, session_id) in slots:
                self._duplicate(
                    session_id, None, f"schedule.{week}.{day} names {session_id!r} twice"
                )
                return
            slots.add((week, day, session_id))
        seen: set[str] = set()
        for session in self.form.sessions:
            if session.id in seen:
                self._duplicate(session.id, None)
                return
            seen.add(session.id)
            exercises: set[str] = set()
            for exercise in (e for line in session.lines for e in _exercises_of(line)):
                if exercise in exercises:
                    self._duplicate(session.id, exercise)
                    return
                exercises.add(exercise)

    def _counted_variants(self) -> None:
        dose = self.form.dose
        if dose is None:
            return
        goal = self.context.goal
        priority = {*dose.lift, *(goal.priority_lifts if goal else ())}
        under: dict[str, list[str]] = {}
        for lift, target in dose.lift.items():
            for variant in target.counts:
                under.setdefault(variant, []).append(lift)
                if self._exercise(variant) is None:
                    self.raise_(
                        "counted_variant_unknown",
                        self.version_scope,
                        {"lift": lift, "exercise_id": variant},
                        f"{lift} counts {variant!r}, which is not in the library and not "
                        "declared in the Draft",
                    )
        for variant, lifts in under.items():
            if len(lifts) > 1 or variant in priority:
                self.raise_(
                    "counted_variant_not_exclusive",
                    self.version_scope,
                    {"exercise_id": variant, "lifts": lifts},
                    f"{variant} is counted under {', '.join(lifts)}; a counted variant counts "
                    "toward one lift and is never itself a priority lift",
                )
                return

    def _duplicate(
        self, session_id: str, exercise_id: str | None, message: str | None = None
    ) -> None:
        what = f"exercise {exercise_id!r} twice in" if exercise_id else "two sessions with id"
        self.raise_(
            "duplicate_id",
            self.version_scope,
            {"session_id": session_id, "exercise_id": exercise_id},
            message or f"{what} {session_id!r}",
        )

    def session(self, session: Session) -> None:
        scope = Scope("session", session_id=session.id)
        params = {"session_id": session.id}
        if session.kind == "rehab":
            self.raise_("rehab_in_version", scope, params, "a rehab session is a niggle's")
            return
        if session.kind == "practice" and session.tier == "core":
            self.raise_("practice_not_optional", scope, params, "a practice is optional")
        coach_led = session.kind == "coach_led"
        if (coach_led and session.lines) or (not coach_led and session.estimated_sets is not None):
            self.raise_(
                "coach_led_has_lines",
                scope,
                params,
                "a coach-led session carries estimated_sets and no lines; others the reverse",
            )
        self._muscles(session.estimated_sets or (), scope, "estimated_sets names")
        self._cadence(session, scope)
        if session.location is not None and session.location not in self.context.racks:
            self.raise_(
                "location_unknown",
                scope,
                {"location": session.location},
                f"location {session.location!r} has no [location.{session.location}]",
            )
        self._session_scheme(session, scope)
        if session.kind != "coach_led":
            for line in session.lines:
                self.line(session, line)

    def _cadence(self, session: Session, scope: Scope) -> None:
        scheduled = session.id in self.form.schedule.scheduled()
        if scheduled and session.cadence is not None:
            self.raise_(
                "cadence_on_scheduled",
                scope,
                {"session_id": session.id, "cadence": session.cadence},
                "a scheduled session is weekly and states no cadence",
            )
        elif not scheduled and session.cadence not in ("standing", "daily"):
            self.raise_(
                "session_unscheduled",
                scope,
                {"session_id": session.id},
                "a session in no rotation week needs cadence standing or daily",
            )

    def _session_scheme(self, session: Session, scope: Scope) -> None:
        if session.kind != "conditioning":
            if session.scheme is not None:
                self.unknown.append(f"session.{session.id}.scheme")
            return
        if session.scheme is None:
            self.raise_(
                "unknown_scheme",
                scope,
                {"scheme": None, "param": None},
                "a conditioning session names a session scheme",
            )
            return
        self._scheme(session.scheme, "session", scope)

    def _scheme(self, ref: SchemeRef, level: str, scope: Scope) -> Scheme | None:
        """The registry row `ref` names, or `None` after raising `unknown_scheme`."""
        if ref.name not in SCHEMES or SCHEMES.get(ref.name).level != level:
            self.raise_(
                "unknown_scheme",
                scope,
                {"scheme": ref.name, "param": None},
                f"{ref.name!r} is no {level} scheme; coach schema --registry schemes",
            )
            return None
        scheme = SCHEMES.get(ref.name)
        for name in ref.params:
            if scheme.param(name) is None:
                return self._bad_param(scheme, name, scope, "is not a param of")
        for param in scheme.params:
            if param.required and param.name not in ref.params:
                return self._bad_param(scheme, param.name, scope, "is required by")
        for name, value in ref.params.items():
            param = cast(Param, scheme.param(name))
            if not _PARAM_TYPES[param.type](value):
                return self._bad_param(scheme, name, scope, f"must be {param.type} for")
        return scheme

    def _bad_param(self, scheme: Scheme, name: str, scope: Scope, why: str) -> None:
        self.raise_(
            "unknown_scheme",
            scope,
            {"scheme": scheme.name, "param": name},
            f"{name!r} {why} {scheme.name}",
        )

    def line(self, session: Session, line: Line) -> None:
        scope = Scope("line", session_id=session.id, exercise_id=line.exercise)
        exercise = self._exercise(line.exercise)
        if exercise is None:
            self.raise_(
                "unknown_exercise",
                scope,
                {"exercise_id": line.exercise},
                f"{line.exercise!r} is not in the library and not declared in the Draft",
            )
            return
        if line.load_mode is not None and line.load_mode not in LOAD_MODES:
            self.raise_(
                "unknown_load_mode",
                scope,
                {"load_mode": line.load_mode},
                f"{line.load_mode!r} is no load mode",
            )
            return
        scheme = self._scheme(line.scheme, "line", scope)
        if line.ladder is None:
            self._set_groups(session, line, line.sets, scheme, scope)
        elif scheme is not None:
            self._ladder(session, line, line.ladder, scheme, scope)
        self._start_load(session, line, exercise, scope)
        self._template(line.exercise, exercise, scope)

    def _exercise(self, id_: str) -> Mapping[str, object] | None:
        stored = self.context.library.get(id_)
        declared = self.form.exercises.get(id_)
        if stored is None and declared is None:
            return None
        return {**(stored or {}), **(declared or {})}

    def _ladder(
        self, session: Session, line: Line, ladder: ExerciseLadder, scheme: Scheme, scope: Scope
    ) -> None:
        if len(ladder.rungs) < 2:
            self.raise_(
                "ladder_too_short",
                scope,
                {"rungs": len(ladder.rungs)},
                f"the ladder on {line.exercise} has one rung; a ladder climbs to a second",
            )
        self._repeated_rung(line, ladder, scope)
        for index, rung in enumerate(ladder.rungs, start=1):
            rung_exercise = self._exercise(rung.exercise) if index > 1 else None
            if index > 1 and rung_exercise is None:
                self.raise_(
                    "rung_exercise_unknown",
                    self.version_scope,
                    {"rung": index, "exercise_id": rung.exercise},
                    f"rung {index} of {line.exercise} in {session.id} names {rung.exercise!r}, "
                    "which is not in the library and not declared in the Draft",
                )
            elif rung_exercise is not None:
                self._template(rung.exercise, rung_exercise, scope)
            self._set_groups(session, line, rung.sets, scheme, scope, rung=index)
            self._rung_start_load(session, line, rung, index, rung_exercise, scope)
            key = _off_rung(rung, ladder.criterion(index))
            if key is not None:
                self.raise_(
                    "advance_criterion_off_rung",
                    scope,
                    {"rung": index, "criterion_key": key},
                    f"rung {index} of {line.exercise} cannot advance on {key}: "
                    "reps on a reps rung, duration_s on a duration rung, manual alone",
                )

    def _repeated_rung(self, line: Line, ladder: ExerciseLadder, scope: Scope) -> None:
        for index, (previous, rung) in enumerate(itertools.pairwise(ladder.rungs), start=2):
            if (rung.exercise, rung.sets, rung.cues) == (
                previous.exercise,
                previous.sets,
                previous.cues,
            ):
                self.raise_(
                    "rung_repeated",
                    scope,
                    {"rung": index, "previous_rung": index - 1},
                    f"rung {index} of {line.exercise} repeats rung {index - 1}: "
                    "a rung on one exercise differs from the one before it in sets or cues",
                )

    def _set_groups(
        self,
        session: Session,
        line: Line,
        groups: Sequence[SetGroup],
        scheme: Scheme | None,
        scope: Scope,
        *,
        rung: int | None = None,
    ) -> None:
        on = "" if rung is None else f" on rung {rung}"
        for index, group in enumerate(groups, start=1):
            allowed = scheme.set_types if scheme else (group.type,)
            if group.type == "test" or group.type not in allowed:
                self.raise_(
                    "set_type_not_allowed",
                    scope,
                    {"set_type": group.type, "scheme": line.scheme.name},
                    f"a {group.type} group{on} is not authored under {line.scheme.name}",
                )
                return
            if group.type == "warm_up":
                path = f"session.{session.id}.line.{line.exercise}.sets.{index}"
                self.unknown.extend(
                    f"{path}.{key}"
                    for key, value in (("duration_s", group.duration_s), ("rpe", group.rpe))
                    if value is not None
                )
        if scheme is None:
            return
        working = [(i, g) for i, g in enumerate(groups, start=1) if g.working]
        if not working and scheme.name != "hold":
            self.raise_(
                "no_working_sets",
                scope,
                {"scheme": scheme.name},
                f"{scheme.name} reads working sets and the line{on} has none",
            )
            return
        shape = _off_shape(scheme, [g for _, g in working])
        if shape is None and rung is not None:
            shape = _off_rung_shape(working[0][1])
        if shape is not None:
            self.raise_(
                "set_groups_off_scheme",
                scope,
                {"scheme": scheme.name, "expected_shape": shape},
                f"the working groups{on} do not fit {scheme.name}: {shape}",
            )
            return
        wanting = working[:1] if scheme.rpe_on == "top" else working
        for index, group in wanting if scheme.rpe_on != "none" else ():
            if group.rpe is None:
                self.raise_(
                    "rpe_missing",
                    scope,
                    {"scheme": scheme.name, "group_index": index},
                    f"set group {index}{on} needs an rpe under {scheme.name}",
                )
                return

    def _start_load(
        self, session: Session, line: Line, exercise: Mapping[str, object], scope: Scope
    ) -> None:
        self._loaded(
            session,
            _Loaded(
                exercise_id=line.exercise,
                exercise=exercise,
                mode=line.load_mode or str(exercise.get("load_mode")),
                start_load=line.start_load,
                key_path=f"session.{session.id}.line.{line.exercise}.start_load",
                needed=line.exercise not in self.context.last_exposures,
                needed_because=(
                    f"{line.exercise} has no Exposure yet, so the line needs a start_load"
                ),
            ),
            scope,
        )

    def _rung_start_load(
        self,
        session: Session,
        line: Line,
        rung: Rung,
        index: int,
        exercise: Mapping[str, object] | None,
        scope: Scope,
    ) -> None:
        """A later rung's load is read in its own exercise's mode. Exposures before the rung's
        start count for nothing on it, so unlike a line's, history never waives it."""
        key_path = f"session.{session.id}.line.{line.exercise}.scheme.rungs.{index}.start_load"
        if index == 1:
            if rung.start_load is not None:
                self.unknown.append(key_path)
            return
        if exercise is None:
            return
        self._loaded(
            session,
            _Loaded(
                exercise_id=rung.exercise,
                exercise=exercise,
                mode=str(exercise.get("load_mode")),
                start_load=rung.start_load,
                key_path=key_path,
                needed=True,
                needed_because=(
                    f"rung {index} of {line.exercise} bears a load, so it needs its own start_load"
                ),
                rung=index,
            ),
            scope,
        )

    def _loaded(self, session: Session, loaded: _Loaded, scope: Scope) -> None:
        if loaded.mode in NO_LOAD_MODES:
            if loaded.start_load is not None:
                self.unknown.append(loaded.key_path)
            return
        if loaded.mode not in LOAD_BEARING_MODES:
            return
        if loaded.start_load is None and loaded.needed:
            self.raise_(
                "start_load_missing",
                scope,
                {"exercise_id": loaded.exercise_id, **loaded.rung_param},
                loaded.needed_because,
                distinct=loaded.distinct,
            )
        location = session.location or self.form.location
        racks = self.context.racks.get(location)
        if loaded.mode not in RACK_MODES or racks is None:
            return
        kind = str(loaded.exercise.get("equipment_kind"))
        rack = racks.get(kind)
        if rack is None:
            self.raise_(
                "equipment_unsupplied",
                scope,
                {"equipment_kind": kind, "location": location},
                f"{location} maps no implement to {kind} in its implements",
                distinct=kind,
            )
            return
        if loaded.start_load is not None and not on_rack(rack, loaded.start_load):
            nearest = list(rows_beside(rack, loaded.start_load))
            self.raise_(
                "start_load_off_rack",
                scope,
                {
                    "start_load": loaded.start_load,
                    "location": location,
                    "nearest_rows": nearest,
                    **loaded.rung_param,
                },
                f"{loaded.start_load} is not on the {kind} rack at {location}; nearest {nearest}",
                distinct=loaded.distinct,
            )

    def _template(self, id_: str, exercise: Mapping[str, object], scope: Scope) -> None:
        if not self.context.hevy_on or id_ not in self.form.exercises:
            return
        if exercise.get("hevy_template_id"):
            return
        missing = [column for column in TEMPLATE_COLUMNS if not exercise.get(column)]
        if missing:
            self.raise_(
                "hevy_template_missing",
                scope,
                {"exercise_id": id_, "missing_columns": missing},
                f"{id_} has no Hevy template and lacks {', '.join(missing)}",
                distinct=id_,
            )
        for column, registry in TEMPLATE_REGISTRIES.items():
            value = exercise.get(column)
            if value and value not in registry:
                self.raise_(
                    "hevy_template_value_unknown",
                    scope,
                    {"exercise_id": id_, "column": column, "value": value},
                    f"{id_} has {column} {value!r}, which Hevy does not accept; "
                    f"coach schema --registry {registry.name}",
                    distinct=f"{id_}#{column}",
                )

    def unknown_keys(self) -> None:
        if self.unknown:
            first, *rest = self.unknown
            more = f" and {', '.join(rest)}" if rest else ""
            self.raise_(
                "unknown_key",
                self.version_scope,
                {"key_path": first},
                f"{first}{more}: not a key of the program form",
            )

    def acknowledgements(self) -> None:
        unmatched = [e.flag for e in self.form.acknowledgements if not self._matches(e.flag)]
        if not unmatched:
            return
        if len(unmatched) == 1:
            [key] = unmatched
            message = f"adopt raised no {key}; remove the [[acknowledge]] entry"
            replaced = self._replaced_by(key)
            if replaced is not None:
                message += (" and " if replaced else ": ") + _instead(key, replaced)
        else:
            message = (
                f"adopt raised no {', '.join(unmatched)}; remove those [[acknowledge]] entries"
            )
            for key in unmatched:
                replaced = self._replaced_by(key)
                if replaced is not None:
                    message += f"; for {key}, {_instead(key, replaced)}"
        self.raise_(
            "acknowledgement_unmatched",
            self.version_scope,
            {"flag_key": unmatched[0], "flag_keys": unmatched},
            message,
        )

    def _matches(self, text: str) -> bool:
        return text in self.context.raised_warnings

    def _replaced_by(self, text: str) -> tuple[str, ...] | None:
        """The keys adopt raised on this Draft for a per-case warning when `text` is that code's
        old version-wide key; None for any other text."""
        code = text.partition("@")[0]
        if code not in PER_CASE_WARNINGS or text != str(FlagKey(code, self.version_scope)):
            return None
        prefix = f"{code}@{FLAGS.get(code).scopes[0]}:{self.context.version_id}/"
        return tuple(sorted(k for k in self.context.raised_warnings if k.startswith(prefix)))


def _instead(text: str, replaced: Sequence[str]) -> str:
    code = text.partition("@")[0]
    if not replaced:
        return f"adopt raised no {code} on this Draft"
    return f"acknowledge each {PER_CASE_WARNINGS[code]} on its own key: {', '.join(replaced)}"


def _exercises_of(line: Line) -> tuple[str, ...]:
    """Each distinct exercise the line can put in a session: its own and its rungs'."""
    return tuple(dict.fromkeys((line.exercise, *line.rung_exercises)))


def _off_rung_shape(group: SetGroup) -> str | None:
    if group.reps is None and group.duration_s is None:
        return "one working group stating reps or duration_s"
    return None


def _off_rung(rung: Rung, criterion: Advance) -> str | None:
    """The criterion key the rung cannot read: `manual` beside another key, `reps` on a duration
    rung, `duration_s` on a reps rung."""
    for advance in (rung.advance, criterion):
        if advance.manual and len(advance.stated()) > 1:
            return "manual"
    on_duration = any(g.duration_s is not None for g in rung.sets if g.working)
    if on_duration and criterion.reps is not None:
        return "reps"
    if not on_duration and criterion.duration_s is not None:
        return "duration_s"
    return None


def _off_shape(scheme: Scheme, groups: Sequence[SetGroup]) -> str | None:
    match scheme.set_groups:
        case "one_working":
            return None if len(groups) == 1 else "exactly one working group"
        case "top_then_backoffs":
            top = groups[0]
            if top.count != 1 or not isinstance(top.reps, int) or len(groups) < 2:
                return "a top group of count 1 and integer reps, then at least one back-off"
            return None
        case "count_only":
            if len(groups) != 1 or groups[0].reps is not None or groups[0].duration_s is not None:
                return "one working group carrying count only"
            return None
        case "any":
            if any(g.reps is None and g.duration_s is None for g in groups):
                return "every working group states reps or duration_s"
            return None


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _positive(value: object) -> bool:
    return _number(value) and cast(float, value) > 0


def _descending_loads(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    loads = cast(list[object], value)
    if not all(_number(v) for v in loads):
        return False
    numbers = [float(cast(float, v)) for v in loads]
    return all(a > b for a, b in itertools.pairwise(numbers))


def _per_exercise(value: object) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    table = cast(dict[object, object], value)
    return all(isinstance(k, str) and _positive(v) for k, v in table.items())


_PARAM_TYPES: Mapping[ParamType, Callable[[object], bool]] = {
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 1,
    "fraction": lambda v: _positive(v) and cast(float, v) <= 1,
    "percent": lambda v: _positive(v) and cast(float, v) <= 100,
    "number": _positive,
    "loads": _descending_loads,
    "per_exercise": _per_exercise,
    "number_or_per_exercise": lambda v: _positive(v) or _per_exercise(v),
    "rungs": lambda v: (
        isinstance(v, list) and all(isinstance(r, dict) for r in cast(list[object], v))
    ),
    "criterion": lambda v: isinstance(v, dict),
}
