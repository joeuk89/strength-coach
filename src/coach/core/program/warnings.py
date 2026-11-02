"""The warnings `program adopt` raises on a filled form (docs/spec/program.md, "Warnings", and
docs/spec/goals.md, "Adopt: the goal checks")."""

from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.closed_week.dose import is_hard
from coach.core.config import WEEKDAYS
from coach.core.flag import Acknowledgement, Flag, FlagKey, Scope, leave, raise_flag
from coach.core.muscles import DOSED_MUSCLES, read_muscles
from coach.core.program.bands import (
    deload_shape,
    dose_bands,
    expected_deload_shape,
    scheme_band,
    scheme_fits,
)
from coach.core.program.checks import AdoptContext
from coach.core.program.estimate import session_estimate
from coach.core.program.form import WEEKDAYS as SCHEDULE_DAYS
from coach.core.program.form import AcknowledgeEntry, Line, ProgramForm, Session
from coach.core.registries.ledger import Reason

LOW_ADHERENCE = ("watch", "low")


def adopt_warnings(form: ProgramForm, context: AdoptContext) -> tuple[Flag, ...]:
    raised = _Warnings(form, context)
    raised.goal()
    raised.priority_lift_absent()
    raised.dose()
    raised.counted_variants()
    raised.deload()
    raised.muscles()
    raised.block()
    raised.retired()
    raised.core_session_added()
    raised.scheme_changes()
    for session in form.sessions:
        raised.session(session)
    return raised.flags()


def leave_warnings(flags: Sequence[Flag], entries: Sequence[AcknowledgeEntry]) -> tuple[Flag, ...]:
    """Each flag left by the entry naming its key, while the entry's params hash, when stated,
    is still the flag's."""
    by_key = {entry.flag: entry for entry in entries}
    return tuple(_left(flag, by_key.get(flag.key)) for flag in flags)


def _left(flag: Flag, entry: AcknowledgeEntry | None) -> Flag:
    if entry is None:
        return flag
    acknowledgement = Acknowledgement(
        FlagKey.parse(entry.flag),
        entry.params_hash or flag.params_hash,
        cast(Reason, entry.because),
        entry.text,
        source="version",
    )
    return leave(flag, (acknowledgement,))


class _Warnings:
    def __init__(self, form: ProgramForm, context: AdoptContext) -> None:
        self.form = form
        self.context = context
        self.found: dict[str, Flag] = {}
        self.version_scope = Scope("version", version_id=context.version_id)
        self.priority_lifts = context.goal.priority_lifts if context.goal else ()

    def flags(self) -> tuple[Flag, ...]:
        return tuple(self.found.values())

    def raise_(self, code: str, scope: Scope, params: Mapping[str, object], message: str) -> None:
        flag = raise_flag(code, scope, params, message)
        self.found.setdefault(flag.key, flag)

    def goal(self) -> None:
        goal = self.context.goal
        if goal is None:
            return
        if self.form.emphasis != goal.kind:
            self.raise_(
                "emphasis_off_goal",
                self.version_scope,
                {"goal_kind": goal.kind, "emphasis": self.form.emphasis},
                f"a {self.form.emphasis} version under a {goal.kind} Goal",
            )

    def priority_lift_absent(self) -> None:
        on_lines = {line.exercise for session in self.form.sessions for line in session.lines}
        absent = [lift for lift in self.priority_lifts if lift not in on_lines]
        if absent:
            self.raise_(
                "priority_lift_absent",
                self.version_scope,
                {"exercise_id": absent[0]},
                f"priority lift {absent[0]} is on no line of the version",
            )

    def dose(self) -> None:
        dose = self.form.dose
        if dose is None:
            return
        bands = dose_bands(self.form.emphasis, self.context.phase)
        targets = [
            ("per_muscle", dose.per_muscle, bands.per_muscle),
            *((lift, target.sets, bands.per_lift) for lift, target in dose.lift.items()),
        ]
        for target_of, target, (low, high) in targets:
            if not low <= target <= high:
                self.raise_(
                    "dose_off_band",
                    self.version_scope,
                    {
                        "target_of": target_of,
                        "target": target,
                        "band": [low, high],
                        "phase": self.context.phase,
                    },
                    f"dose {target_of} = {target} is outside {low}-{high} hard sets a week",
                )
                return

    def counted_variants(self) -> None:
        dose = self.form.dose
        if dose is None:
            return
        for lift, target in dose.lift.items():
            for variant in target.counts:
                patterns = [self._pattern(lift), self._pattern(variant)]
                primary = [self._primary(lift), self._primary(variant)]
                if patterns[0] != patterns[1] or set(primary[0]) != set(primary[1]):
                    self.raise_(
                        "counted_variant_off_pattern",
                        self.version_scope,
                        {
                            "lift": lift,
                            "variant": variant,
                            "patterns": patterns,
                            "primary_muscles": primary,
                        },
                        f"{lift} counts {variant}, whose pattern or primary muscles differ",
                    )
                    return

    def _fields(self, exercise_id: str) -> Mapping[str, object]:
        declared = self.form.exercises.get(exercise_id) or {}
        stored = self.context.library.get(exercise_id) or {}
        return {**stored, **declared}

    def _pattern(self, exercise_id: str) -> object:
        return self._fields(exercise_id).get("pattern")

    def _primary(self, exercise_id: str) -> list[str]:
        muscles = read_muscles(self._fields(exercise_id).get("muscles"))
        return muscles["primary"] if muscles else []

    def deload(self) -> None:
        if self.form.deload is None:
            return
        policy = deload_shape(self.form.deload)
        expected = expected_deload_shape(self.form.emphasis)
        if policy != expected:
            self.raise_(
                "deload_off_emphasis",
                self.version_scope,
                {"deload_policy": policy, "expected_shape": expected},
                f"the deload {policy} departs from the {self.form.emphasis} shape {expected}",
            )

    def muscles(self) -> None:
        core = [session for session in self.form.sessions if session.tier == "core"]
        trained: set[str] = set()
        for session in core:
            trained.update(m for m, sets in (session.estimated_sets or {}).items() if sets > 0)
            for line in session.lines:
                if _hard(line):
                    trained.update(self._muscles(line.exercise))
        missing = [muscle for muscle in DOSED_MUSCLES if muscle not in trained]
        if missing:
            self.raise_(
                "muscle_no_hard_sets",
                self.version_scope,
                {"muscle": missing[0], "sessions_searched": [s.id for s in core]},
                f"no core session gives {missing[0]} a hard set",
            )

    def _muscles(self, exercise_id: str) -> list[str]:
        declared = self.form.exercises.get(exercise_id) or {}
        stored = self.context.library.get(exercise_id) or {}
        muscles = declared.get("muscles") or stored.get("muscles")
        if not isinstance(muscles, dict):
            return []
        table = cast(dict[str, list[str]], muscles)
        return [*table.get("primary", []), *table.get("secondary", [])]

    def block(self) -> None:
        block = self.context.open_block
        if self.form.kind == "redesign" and block is not None:
            self.raise_(
                "block_open_at_redesign",
                self.version_scope,
                {"block_id": block.id, "hard_weeks": block.hard_weeks},
                f"a redesign closes {block.id} after {block.hard_weeks} hard weeks",
            )

    def retired(self) -> None:
        previous = self.context.previous
        if previous is None:
            return
        gone = [s.id for s in previous.sessions if self.form.session(s.id) is None]
        if gone:
            self.raise_(
                "session_retired",
                self.version_scope,
                {"session_id": gone[0], "routine_id": self.context.routines.get(gone[0])},
                f"{gone[0]} is in the version in force and not in this one",
            )

    def core_session_added(self) -> None:
        """rn:deloads.7: under 80 % adherence no new recurring session is added."""
        adherence, previous = self.context.adherence, self.context.previous
        if adherence is None or adherence.state not in LOW_ADHERENCE or previous is None:
            return
        core_before = {s.id for s in previous.sessions if s.tier == "core"}
        for session in self.form.sessions:
            if session.tier == "core" and session.id not in core_before:
                self.raise_(
                    "core_session_added_low_adherence",
                    Scope("session", session_id=session.id),
                    {
                        "session_id": session.id,
                        "adherence": adherence.figure,
                        "weeks": adherence.weeks,
                    },
                    f"{session.id} adds a core session while adherence is {adherence.state}",
                )

    def scheme_changes(self) -> None:
        """goals.md, "Response to a cadence signal": a scheme changes only where a cadence signal
        lists the new one."""
        previous = self.context.previous
        if previous is None:
            return
        before = {line.exercise: line.scheme.name for s in previous.sessions for line in s.lines}
        for session in self.form.sessions:
            for line in session.lines:
                was = before.get(line.exercise)
                if was is None or was == line.scheme.name:
                    continue
                signal = self.context.signals.get(line.exercise)
                may = cast(list[str], signal.params["may_schemes"]) if signal else []
                if line.scheme.name in may:
                    continue
                self.raise_(
                    "scheme_change_off_signal",
                    Scope("line", session_id=session.id, exercise_id=line.exercise),
                    {
                        "previous_scheme": was,
                        "new_scheme": line.scheme.name,
                        "signal_key": signal.key if signal else None,
                        "may_schemes": may,
                    },
                    f"{line.exercise} moves from {was} to {line.scheme.name}"
                    + (
                        f", outside {signal.key}'s may_schemes {may}"
                        if signal
                        else " with no cadence signal open"
                    ),
                )

    def session(self, session: Session) -> None:
        scope = Scope("session", session_id=session.id)
        self._unavailable_day(session, scope)
        self._minutes(session, scope)
        self._superset_rests(session, scope)
        for line in session.lines:
            self._start_load(session, line)
        if session.kind != "lifting":
            return
        for line in session.lines:
            self._scheme(session, line)
        self._priority_first(session, scope)

    def _unavailable_day(self, session: Session, scope: Scope) -> None:
        available = self.context.available_days
        for _, day, session_id in self.form.schedule.slots():
            weekday = WEEKDAYS[SCHEDULE_DAYS.index(day)]
            if session_id == session.id and weekday not in available:
                self.raise_(
                    "session_on_unavailable_day",
                    scope,
                    {
                        "session_id": session.id,
                        "weekday": weekday,
                        "available_days": list(available),
                    },
                    f"{session.id} is scheduled on {weekday}, outside [athlete].available_days",
                )
                return

    def _minutes(self, session: Session, scope: Scope) -> None:
        estimate = session_estimate(session.lines)
        if session.minutes is None or estimate is None:
            return
        if estimate > session.minutes:
            self.raise_(
                "session_over_minutes",
                scope,
                {"estimate": estimate, "minutes": session.minutes},
                f"{session.id} takes about {estimate} minutes against {session.minutes}",
            )

    def _superset_rests(self, session: Session, scope: Scope) -> None:
        supersets: dict[str, list[int]] = {}
        for line in session.lines:
            if line.superset is not None:
                supersets.setdefault(line.superset, []).append(line.rest_s)
        for label, rests in supersets.items():
            # A 0 rest is a line performed straight into its partner.
            if len({rest for rest in rests if rest}) > 1:
                self.raise_(
                    "superset_rest_differs",
                    scope,
                    {"superset": label, "rest_values": rests},
                    f"superset {label} in {session.id} rests {rests} seconds",
                )
                return

    def _start_load(self, session: Session, line: Line) -> None:
        exposure = self.context.last_exposures.get(line.exercise)
        if line.start_load is None or exposure is None or exposure.top_load is None:
            return
        load = exposure.top_load
        if load.amount != line.start_load:
            self.raise_(
                "start_load_ignored",
                Scope("line", session_id=session.id, exercise_id=line.exercise),
                {
                    "start_load": line.start_load,
                    "last_exposure_load": load.amount,
                    "exposure": exposure.ref,
                },
                f"history wins: {line.exercise} was last {load.amount}, not {line.start_load}",
            )

    def _priority_first(self, session: Session, scope: Scope) -> None:
        working = [line.exercise for line in session.lines if line.working_groups()]
        for position, exercise in enumerate(working, start=1):
            if exercise not in self.priority_lifts:
                continue
            if any(ahead not in self.priority_lifts for ahead in working[: position - 1]):
                self.raise_(
                    "priority_lift_not_first",
                    scope,
                    {"exercise_id": exercise, "position": position},
                    f"priority lift {exercise} is working line {position} of {session.id}",
                )
                return

    def _scheme(self, session: Session, line: Line) -> None:
        priority = line.exercise in self.priority_lifts
        if scheme_fits(line, priority):
            return
        band = list(scheme_band(priority))
        self.raise_(
            "scheme_off_emphasis",
            Scope("line", session_id=session.id, exercise_id=line.exercise),
            {"scheme": line.scheme.name, "emphasis": self.form.emphasis, "expected_band": band},
            f"{line.scheme.name} on {line.exercise} is outside the band {band}",
        )


def _hard(line: Line) -> bool:
    return any(is_hard(group.rpe) for group in line.working_groups())
