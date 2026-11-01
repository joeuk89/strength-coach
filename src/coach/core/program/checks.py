"""The violations `program adopt` raises on a form (docs/spec/program.md, "Violations")."""

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from coach.core.errors import Invalid
from coach.core.flag import Flag, FlagKey, Scope, raise_flag
from coach.core.goal import Goal
from coach.core.program.form import (
    LOAD_BEARING_MODES,
    RACK_MODES,
    Line,
    ProgramForm,
    SchemeRef,
    Session,
    SetGroup,
)
from coach.core.rack import Rack
from coach.core.registries.flags import ADOPT_WARNINGS
from coach.core.registries.program import LOAD_MODES
from coach.core.registries.schemes import SCHEMES, Scheme

TEMPLATE_COLUMNS = ("hevy_title", "hevy_exercise_type", "hevy_equipment", "hevy_muscle_group")
NO_LOAD_MODES = ("bodyweight", "duration", "distance")
ADOPT_WARNING_CODES = frozenset(code.name for code in ADOPT_WARNINGS)
# The adopt warnings this engine raises; an acknowledgement of any other adopt warning is not
# judged yet, because adopt cannot tell whether it would have raised it.
JUDGED_ADOPT_WARNINGS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AdoptContext:
    """What the checks read beside the form, as values. `racks` maps each location in
    `coach.toml` to the rack of every equipment kind it supplies."""

    version_id: str
    library: Mapping[str, Mapping[str, object]]
    racks: Mapping[str, Mapping[str, Rack]]
    exposed: frozenset[str] = frozenset()
    goal: Goal | None = None
    hevy_on: bool = False
    raised_warnings: frozenset[str] = field(default_factory=frozenset[str])


def violations(
    form: ProgramForm, context: AdoptContext, unknown_keys: Sequence[str] = ()
) -> tuple[Flag, ...]:
    check = _Checks(form, context, list(unknown_keys))
    check.version()
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

    def raise_(self, code: str, scope: Scope, params: Mapping[str, object], message: str) -> None:
        flag = raise_flag(code, scope, params, message)
        self.found.setdefault(flag.key, flag)

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

    def _duplicate_ids(self) -> None:
        seen: set[str] = set()
        for session in self.form.sessions:
            if session.id in seen:
                self._duplicate(session.id, None)
                return
            seen.add(session.id)
            exercises: set[str] = set()
            for line in session.lines:
                if line.exercise in exercises:
                    self._duplicate(session.id, line.exercise)
                    return
                exercises.add(line.exercise)

    def _duplicate(self, session_id: str, exercise_id: str | None) -> None:
        what = f"exercise {exercise_id!r} twice in" if exercise_id else "two sessions with id"
        self.raise_(
            "duplicate_id",
            self.version_scope,
            {"session_id": session_id, "exercise_id": exercise_id},
            f"{what} {session_id!r}",
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
        rungs = ref.params.get("rungs")
        if "rungs" in ref.params and not _descending_loads(rungs):
            return self._bad_param(scheme, "rungs", scope, "must list loads, descending, for")
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
        self._set_groups(session, line, scheme, scope)
        self._start_load(session, line, exercise, scope)
        self._template(line, exercise, scope)

    def _exercise(self, id_: str) -> Mapping[str, object] | None:
        stored = self.context.library.get(id_)
        declared = self.form.exercises.get(id_)
        if stored is None and declared is None:
            return None
        return {**(stored or {}), **(declared or {})}

    def _set_groups(
        self, session: Session, line: Line, scheme: Scheme | None, scope: Scope
    ) -> None:
        for index, group in enumerate(line.sets, start=1):
            allowed = scheme.set_types if scheme else (group.type,)
            if group.type == "test" or group.type not in allowed:
                self.raise_(
                    "set_type_not_allowed",
                    scope,
                    {"set_type": group.type, "scheme": line.scheme.name},
                    f"a {group.type} group is not authored under {line.scheme.name}",
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
        working = [(i, g) for i, g in enumerate(line.sets, start=1) if g.working]
        if not working and scheme.name != "hold":
            self.raise_(
                "no_working_sets",
                scope,
                {"scheme": scheme.name},
                f"{scheme.name} reads working sets and the line has none",
            )
            return
        shape = _off_shape(scheme, [g for _, g in working])
        if shape is not None:
            self.raise_(
                "set_groups_off_scheme",
                scope,
                {"scheme": scheme.name, "expected_shape": shape},
                f"the working groups do not fit {scheme.name}: {shape}",
            )
            return
        wanting = working[:1] if scheme.rpe_on == "top" else working
        for index, group in wanting if scheme.rpe_on != "none" else ():
            if group.rpe is None:
                self.raise_(
                    "rpe_missing",
                    scope,
                    {"scheme": scheme.name, "group_index": index},
                    f"set group {index} needs an rpe under {scheme.name}",
                )
                return

    def _start_load(
        self, session: Session, line: Line, exercise: Mapping[str, object], scope: Scope
    ) -> None:
        mode = line.load_mode or str(exercise.get("load_mode"))
        if mode in NO_LOAD_MODES:
            if line.start_load is not None:
                self.unknown.append(f"session.{session.id}.line.{line.exercise}.start_load")
            return
        if mode not in LOAD_BEARING_MODES:
            return
        if line.start_load is None and line.exercise not in self.context.exposed:
            self.raise_(
                "start_load_missing",
                scope,
                {"exercise_id": line.exercise},
                f"{line.exercise} has no Exposure yet, so the line needs a start_load",
            )
        location = session.location or self.form.location
        racks = self.context.racks.get(location)
        if mode not in RACK_MODES or racks is None:
            return
        kind = str(exercise.get("equipment_kind"))
        rack = racks.get(kind)
        if rack is None:
            self.raise_(
                "equipment_unsupplied",
                scope,
                {"equipment_kind": kind, "location": location},
                f"{location} maps no implement to {kind} in its implements",
            )
            return
        if line.start_load is not None and not rack.rows_within(line.start_load, line.start_load):
            nearest = [
                row.load
                for row in (rack.row_below(line.start_load), rack.row_above(line.start_load))
                if row
            ]
            self.raise_(
                "start_load_off_rack",
                scope,
                {"start_load": line.start_load, "location": location, "nearest_rows": nearest},
                f"{line.start_load} is not on the {kind} rack at {location}; nearest {nearest}",
            )

    def _template(self, line: Line, exercise: Mapping[str, object], scope: Scope) -> None:
        if not self.context.hevy_on or line.exercise not in self.form.exercises:
            return
        if exercise.get("hevy_template_id"):
            return
        missing = [column for column in TEMPLATE_COLUMNS if not exercise.get(column)]
        if missing:
            self.raise_(
                "hevy_template_missing",
                scope,
                {"exercise_id": line.exercise, "missing_columns": missing},
                f"{line.exercise} has no Hevy template and lacks {', '.join(missing)}",
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
        for entry in self.form.acknowledgements:
            if not self._matches(entry.flag):
                self.raise_(
                    "acknowledgement_unmatched",
                    self.version_scope,
                    {"flag_key": entry.flag},
                    f"adopt raised no {entry.flag}; remove the [[acknowledge]] entry",
                )
                return

    def _matches(self, text: str) -> bool:
        try:
            key = FlagKey.parse(text)
        except Invalid:
            return False
        if text in self.context.raised_warnings:
            return True
        code_row_scopes = _adopt_scopes(key.code)
        return (
            key.code not in JUDGED_ADOPT_WARNINGS
            and key.scope.kind in code_row_scopes
            and not key.scope.dated
            and self._names_the_draft(key.scope)
        )

    def _names_the_draft(self, scope: Scope) -> bool:
        resolvers: dict[str, Callable[[Scope], bool]] = {
            "version": lambda s: s.version_id == self.context.version_id,
            "session": lambda s: self.form.session(str(s.session_id)) is not None,
            "line": self._names_a_line,
        }
        resolve = resolvers.get(scope.kind)
        return resolve is not None and resolve(scope)

    def _names_a_line(self, scope: Scope) -> bool:
        session = self.form.session(str(scope.session_id))
        return session is not None and any(
            line.exercise == scope.exercise_id for line in session.lines
        )


def _adopt_scopes(code: str) -> tuple[str, ...]:
    return next((row.scopes for row in ADOPT_WARNINGS if row.name == code), ())


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


def _descending_loads(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    loads = cast(list[object], value)
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in loads):
        return False
    numbers = [float(cast(float, v)) for v in loads]
    return all(a > b for a, b in itertools.pairwise(numbers))
