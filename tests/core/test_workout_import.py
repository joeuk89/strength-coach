import datetime
from zoneinfo import ZoneInfo

from coach.core.mirror import LoggedSet, Workout, WorkoutEvent
from coach.core.workout_import import Presence, event_pull_changes, full_pull_changes, version_of

NOW = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=datetime.UTC)
LONDON = ZoneInfo("Europe/London")
SYDNEY = ZoneInfo("Australia/Sydney")


def a_workout(workout_id: str, updated_at: str = "2026-10-26T19:05:00.000Z") -> Workout:
    logged = LoggedSet(0, "T", "Squat", "working", "normal", 100.0, 5, None, None, None, None)
    return Workout(
        id=workout_id,
        updated_at=updated_at,
        title=None,
        routine_id=None,
        started_at="2026-10-26T18:00:00+00:00",
        ended_at="2026-10-26T18:47:20+00:00",
        notes=None,
        sets=(logged,),
        raw="{}",
    )


def updated(workout: Workout) -> WorkoutEvent:
    return WorkoutEvent("updated", workout.id, workout, None)


def deleted(workout_id: str) -> WorkoutEvent:
    return WorkoutEvent("deleted", workout_id, None, "2026-10-29T09:00:00Z")


def test_a_version_carries_the_local_date_minutes_and_a_utc_updated_at() -> None:
    london = version_of(a_workout("w1", "2026-10-26T20:05:00.123+01:00"), LONDON)
    sydney = version_of(a_workout("w1"), SYDNEY)

    assert (london.date, london.minutes, london.updated_at) == (
        "2026-10-26",
        47,
        "2026-10-26T19:05:00Z",
    )
    assert sydney.date == "2026-10-27"


def test_a_delete_event_for_a_workout_never_stored_changes_nothing() -> None:
    changes = event_pull_changes({}, [deleted("w9")], NOW, LONDON)

    assert (changes.versions, changes.tombstones) == ((), ())


def test_an_update_then_a_delete_in_one_pull_stores_the_version_and_its_tombstone() -> None:
    changes = event_pull_changes({}, [updated(a_workout("w1")), deleted("w1")], NOW, LONDON)

    assert [v.id for v in changes.versions] == ["w1"]
    assert [(t.kind, t.source) for t in changes.tombstones] == [("gone", "event")]


def test_a_known_version_listed_again_is_not_a_new_version() -> None:
    stored = {"w1": Presence(frozenset({"2026-10-26T19:05:00Z"}))}

    changes = full_pull_changes(stored, [a_workout("w1")], NOW, LONDON)

    assert (changes.versions, changes.tombstones, changes.new, changes.versioned) == ((), (), 0, 0)


def test_a_gone_workout_stays_gone_while_a_full_pull_still_misses_it() -> None:
    stored = {"w1": Presence(frozenset({"2026-10-26T19:05:00Z"}), gone=True)}

    assert full_pull_changes(stored, [], NOW, LONDON).tombstones == ()


def test_events_newest_first_apply_oldest_first_so_an_edit_then_a_delete_ends_gone() -> None:
    stored = {"w1": Presence(frozenset({"2026-10-26T19:05:00Z"}))}
    edited = a_workout("w1", "2026-10-28T08:00:00Z")

    changes = event_pull_changes(stored, [deleted("w1"), updated(edited)], NOW, LONDON)

    assert [v.updated_at for v in changes.versions] == ["2026-10-28T08:00:00Z"]
    assert [t.kind for t in changes.tombstones] == ["gone"]


def test_a_workout_logged_and_deleted_in_one_window_ends_gone_whatever_the_page_order() -> None:
    changes = event_pull_changes({}, [deleted("w1"), updated(a_workout("w1"))], NOW, LONDON)

    assert [v.id for v in changes.versions] == ["w1"]
    assert [t.kind for t in changes.tombstones] == ["gone"]


def test_a_delete_then_an_edit_of_a_stored_workout_in_one_pull_writes_no_tombstone() -> None:
    stored = {"w1": Presence(frozenset({"2026-10-26T19:05:00Z"}))}
    edited = a_workout("w1", "2026-10-29T10:00:00Z")

    changes = event_pull_changes(stored, [deleted("w1"), updated(edited)], NOW, LONDON)

    assert (changes.tombstones, changes.versioned) == ((), 1)


def test_an_edit_then_a_delete_of_a_gone_workout_in_one_pull_writes_no_tombstone() -> None:
    stored = {"w1": Presence(frozenset({"2026-10-26T19:05:00Z"}), gone=True)}
    edited = a_workout("w1", "2026-10-28T08:00:00Z")

    changes = event_pull_changes(stored, [updated(edited), deleted("w1")], NOW, LONDON)

    assert changes.tombstones == ()
