"""The three activity rules (docs/spec/week.md, "Activity rules") and the plan's status-span
drop suggestion."""

import datetime
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from coach.core.flag import Flag, Scope, raise_flag
from coach.core.planned_week import DAYS_IN_WEEK, week_monday
from coach.core.prescription import SessionPrescription, StatusSpan
from coach.core.program.form import Reps

# rn:running-load.5: quality activities, runs and conditioning together, capped at 2 a week.
QUALITY_CAP = 2
# rn:running-load.1: a run over 1.10 times the longest in the previous 30 days.
SPIKE_RATIO = 1.10
SPIKE_LOOKBACK_DAYS = 30
# rn:running-load.4: judged only once 14 days of activity history exist before the run.
SPIKE_HISTORY_DAYS = 14
RUN = "run"
# rn:concurrent-training.5: a heavy squat or hinge session has a working set at RPE 7 or above,
# or of 6 reps or fewer when no RPE is set.
HEAVY_PATTERNS = ("squat", "hinge")
HEAVY_RPE = 7
HEAVY_REPS = 6
# The statuses a session is suggested off; a whole-week `no_training` span plans nothing.
DROP_SPANS = ("ill", "injured", "travel")


@dataclass(frozen=True)
class LoggedActivity:
    """An Activity, or a conditioning workout's Activity view; `id` is the row's or the
    workout's."""

    id: str
    date: datetime.date
    kind: str
    minutes: int | None
    rpe: float
    quality: bool
    distance_km: float | None = None


def activity_cap_exceeded(
    activities: Iterable[LoggedActivity], monday: datetime.date
) -> Flag | None:
    sunday = monday + datetime.timedelta(days=DAYS_IN_WEEK - 1)
    quality = sorted(
        (a for a in activities if a.quality and monday <= a.date <= sunday), key=lambda a: a.date
    )
    if len(quality) <= QUALITY_CAP:
        return None
    return raise_flag(
        "activity_cap_exceeded",
        Scope("week", monday),
        {"cap": QUALITY_CAP, "observed": len(quality), "activities": [a.id for a in quality]},
        f"{len(quality)} quality activities in the week of {monday}, over the cap of {QUALITY_CAP}",
        rn="rn:running-load.5",
    )


def run_spikes(activities: Sequence[LoggedActivity], *, since: datetime.date) -> list[Flag]:
    """Every run on or after `since` over 1.10 times the longest run in the 30 days before it."""
    first = min((a.date for a in activities), default=None)
    runs = [a for a in activities if a.kind == RUN and a.distance_km is not None]
    found: list[Flag] = []
    for run in runs:
        if run.date < since or first is None:
            continue
        if (run.date - first).days < SPIKE_HISTORY_DAYS:
            continue
        lookback = run.date - datetime.timedelta(days=SPIKE_LOOKBACK_DAYS)
        longest = max(
            (r.distance_km or 0 for r in runs if lookback <= r.date < run.date), default=None
        )
        if not longest:
            continue
        exact = (run.distance_km or 0) / longest
        if exact > SPIKE_RATIO:
            ratio = round(exact, 2)
            found.append(
                raise_flag(
                    "run_spike",
                    Scope("workout", workout_id=run.id),
                    {"distance": run.distance_km, "longest_30_days": longest, "ratio": ratio},
                    f"the {run.distance_km:g} km run on {run.date} is {ratio:g} times the "
                    f"longest of the previous {SPIKE_LOOKBACK_DAYS} days",
                    rn="rn:running-load.1",
                )
            )
    return found


def quality_stack(
    sessions: Sequence[SessionPrescription],
    *,
    quality: Collection[str],
    patterns: Mapping[str, str | None],
) -> list[Flag]:
    """A planned quality conditioning session the day before a heavy squat or hinge session, or on
    the day of any lifting session. Planned sessions carry no time of day, so the day before
    stands for "within 24 hours" and the same day for "under 6 hours between"."""
    found: list[Flag] = []
    for conditioning in sessions:
        planned = conditioning.session
        if planned.kind != "conditioning" or planned.session_id not in quality:
            continue
        for lifting in sessions:
            other = lifting.session
            if other.kind != "lifting":
                continue
            same_day = other.date == planned.date
            next_day = other.date - planned.date == datetime.timedelta(days=1)
            if same_day or (next_day and _heavy(lifting, patterns)):
                found.append(_drop(conditioning, lifting, same_day))
                break
    return found


def status_span_drops(
    sessions: Iterable[SessionPrescription], spans: Sequence[StatusSpan]
) -> list[Flag]:
    return [
        raise_flag(
            "session_drop_suggested",
            _scope(prescribed),
            {"reason": "status_span", "evidence": []},
            f"{prescribed.session.session_id} on {prescribed.session.date} falls in a "
            "status span; drop or move it",
        )
        for prescribed in sessions
        if prescribed.session.tier == "core"
        and any(s.kind in DROP_SPANS and s.covers(prescribed.session.date) for s in spans)
    ]


def _heavy(prescribed: SessionPrescription, patterns: Mapping[str, str | None]) -> bool:
    return any(
        _heavy_set(group.rpe, _bottom(group.reps))
        for line in prescribed.lines
        if patterns.get(line.exercise_id) in HEAVY_PATTERNS
        for group in line.groups
        if group.type == "working"
    )


def _heavy_set(rpe: float | None, reps: int | None) -> bool:
    if rpe is not None:
        return rpe >= HEAVY_RPE
    return reps is not None and reps <= HEAVY_REPS


def _bottom(reps: Reps | None) -> int | None:
    if isinstance(reps, tuple):
        return reps[0]
    if isinstance(reps, str):
        return int(reps.rstrip("+"))
    return reps


def _drop(conditioning: SessionPrescription, lifting: SessionPrescription, same_day: bool) -> Flag:
    planned, other = conditioning.session, lifting.session
    return raise_flag(
        "session_drop_suggested",
        _scope(conditioning),
        {
            "reason": "quality_stack",
            "evidence": [
                _ref(planned.date, planned.session_id),
                _ref(other.date, other.session_id),
            ],
        },
        f"quality {planned.session_id} on {planned.date} sits "
        f"{'on the same day as' if same_day else 'the day before heavy'} {other.session_id}",
        rn="rn:concurrent-training.4" if same_day else "rn:concurrent-training.5",
    )


def _scope(prescribed: SessionPrescription) -> Scope:
    planned = prescribed.session
    return Scope("session", week_monday(planned.date), session_id=planned.session_id)


def _ref(on: datetime.date, session_id: str) -> str:
    return f"planned_session:{on.isoformat()}/{session_id}"
