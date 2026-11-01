from coach.core.write_plan import moved_routines, resumed_write_plan_hash

APPROVED_AT = "2026-10-30T12:00:00Z"


def moved(imports: dict[str, str], own_writes: dict[str, str]) -> tuple[str, ...]:
    return moved_routines(("r1",), approved_at=APPROVED_AT, imports=imports, own_writes=own_writes)


def test_a_routine_imported_after_approval_that_the_push_never_wrote_has_moved() -> None:
    assert moved({"r1": "2026-10-30T13:00:00Z"}, {}) == ("r1",)


def test_a_routine_imported_before_approval_has_not_moved() -> None:
    assert moved({"r1": "2026-10-30T11:00:00Z"}, {}) == ()


def test_the_pushs_own_read_back_is_not_a_move() -> None:
    at = "2026-10-31T12:00:00Z"
    assert moved({"r1": at}, {"r1": at}) == ()


def test_a_later_check_that_left_the_routine_unchanged_is_not_a_move() -> None:
    assert moved({"r1": "2026-10-31T12:00:00Z"}, {"r1": "2026-11-01T12:00:00Z"}) == ()


def test_an_import_after_the_pushs_last_write_is_a_move() -> None:
    assert moved({"r1": "2026-11-01T13:00:00Z"}, {"r1": "2026-11-01T12:00:00Z"}) == ("r1",)


def test_the_resumed_hash_is_the_approved_one_until_a_routine_moves() -> None:
    assert resumed_write_plan_hash("sha256:a", {}) == "sha256:a"
    assert resumed_write_plan_hash("sha256:a", {"r1": "2026-11-01T13:00:00Z"}) not in {
        "sha256:a",
        resumed_write_plan_hash("sha256:a", {"r1": "2026-11-02T13:00:00Z"}),
    }
