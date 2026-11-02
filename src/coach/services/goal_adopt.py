import datetime
from dataclasses import dataclass, replace

from coach.core.clock import Clock
from coach.core.errors import Invalid
from coach.core.goal import GoalDraft, goal_diff, parse_goal_draft
from coach.store import exercises, goals, phases
from coach.store.connection import Connection
from coach.store.ids import next_ids
from coach.store.transaction import transaction


@dataclass(frozen=True)
class GoalAdoptResult:
    draft_hash: str
    goal_id: str
    kind: str
    priority_lifts: tuple[str, ...]
    milestones: tuple[str, ...]
    superseded: str | None
    phase_opened: str | None
    phase_closed: str | None
    diff: dict[str, object] | None
    dry_run: bool = False
    no_op: bool = False


def goal_adopt(
    conn: Connection, data: bytes, *, file: str, clock: Clock, dry_run: bool = False
) -> GoalAdoptResult:
    """Record a Goal from its Draft, superseding the current one, and open or close the Phase.
    A Draft whose hash is already stored writes nothing (verbs.md, "Re-run safety"). A dry run
    writes and rolls back."""
    draft = parse_goal_draft(data, file=file)
    with transaction(conn, commit=not dry_run):
        goal_id = goals.id_by_draft(conn, draft.hash)
        no_op = goal_id is not None
        if goal_id is None:
            goal_id = _write(conn, draft, clock)
        return replace(_result(conn, draft.hash, goal_id), dry_run=dry_run, no_op=no_op)


def _write(conn: Connection, draft: GoalDraft, clock: Clock) -> str:
    _check_exercises(conn, draft)
    today = clock.today().isoformat()
    recorded_at = clock.now().astimezone(datetime.UTC).isoformat(timespec="seconds")
    (goal_id,) = next_ids(conn, "goal", "g-", 1)
    ref = f"goal:{goal_id}"
    open_ = phases.open_phase(conn)
    if draft.close:
        if open_ is None:
            raise Invalid("state_conflict", f"{draft.file}: [phase] closes, but no Phase is open")
        phases.close(conn, open_.id, closed=today, closed_by=ref, because=draft.close.because)
        open_ = None
    if draft.open and open_:
        raise Invalid(
            "phase_already_open",
            f"{draft.file}: Phase {open_.id} ({open_.kind}) is open; close it in the same "
            "[phase] table before opening another",
        )
    goals.insert(
        conn,
        id_=goal_id,
        goal=draft.goal,
        milestone_ids=next_ids(conn, "milestone", "m-", len(draft.goal.milestones)),
        adopted=today,
        draft_hash=draft.hash,
        recorded_at=recorded_at,
    )
    if draft.open:
        (phase_id,) = next_ids(conn, "phase", "ph-", 1)
        phases.insert(
            conn,
            id_=phase_id,
            phase=draft.open,
            opened=today,
            opened_by=ref,
            draft_hash=draft.hash,
            recorded_at=recorded_at,
        )
    return goal_id


def _check_exercises(conn: Connection, draft: GoalDraft) -> None:
    for exercise in dict.fromkeys(draft.exercises()):
        if exercises.get(conn, exercise) is None:
            raise Invalid(
                "unknown_exercise",
                f"{draft.file}: {exercise!r} is not in the library; use a library id or "
                "declare it with an [[exercise]] record first",
            )


def _result(conn: Connection, draft_hash: str, goal_id: str) -> GoalAdoptResult:
    stored = goals.get(conn, goal_id)
    assert stored is not None
    previous_id = goals.previous_of(conn, goal_id)
    previous = goals.get(conn, previous_id) if previous_id else None
    ref = f"goal:{goal_id}"
    return GoalAdoptResult(
        draft_hash=draft_hash,
        goal_id=goal_id,
        kind=stored.goal.kind,
        priority_lifts=stored.goal.priority_lifts,
        milestones=stored.milestone_ids,
        superseded=previous_id,
        phase_opened=phases.opened_by(conn, ref),
        phase_closed=phases.closed_by(conn, ref),
        diff=goal_diff(previous.goal if previous else None, stored.goal),
    )
