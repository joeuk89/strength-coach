from coach.core.hevy_actions import (
    HevyActions,
    MappedRoutine,
    ProjectedSession,
    RoutineAction,
    hevy_actions,
    spare_routines,
)


def test_the_oldest_spare_no_other_session_holds_is_taken_before_a_post() -> None:
    routine_map = (
        MappedRoutine("old_a", "r-1", "retired", "2026-10-05T10:00:00Z"),
        MappedRoutine("old_b", "r-2", "retired", "2026-09-28T10:00:00Z"),
        MappedRoutine("old_c", "r-3", "retired", "2026-09-01T10:00:00Z"),
        MappedRoutine("pull", "r-3", "active", "2026-10-12T10:00:00Z"),
    )

    actions = hevy_actions(
        (
            ProjectedSession("push", False),
            ProjectedSession("legs", False),
            ProjectedSession("core", True),
        ),
        routine_map=routine_map,
        folders={"program", "standing", "retired"},
        sessions_in_force={"push", "legs", "core", "pull"},
        templates={},
    )

    assert spare_routines(routine_map) == ("r-2", "r-1")
    assert actions == HevyActions(
        creates=(
            RoutineAction("push", "r-2"),
            RoutineAction("legs", "r-1"),
            RoutineAction("core", None),
        )
    )
    assert actions.touched_routines == ("r-2", "r-1")
