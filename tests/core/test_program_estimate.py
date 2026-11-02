from coach.core.program.estimate import session_estimate
from coach.core.program.form import Line, SchemeRef, SetGroup

HOLD = SchemeRef("hold")


def a_line(*sets: SetGroup, rest_s: int = 120) -> Line:
    return Line("bb_bench_press", sets, rest_s, HOLD)


def test_a_set_without_a_duration_takes_forty_seconds_before_its_rest() -> None:
    assert session_estimate([a_line(SetGroup(3), rest_s=20)]) == 3


def test_a_stated_duration_replaces_the_default_set_time() -> None:
    assert session_estimate([a_line(SetGroup(2, duration_s=70), rest_s=50)]) == 4


def test_every_group_of_every_line_counts_and_the_total_rounds_up_to_a_minute() -> None:
    lines = [
        a_line(SetGroup(1, type="warm_up"), SetGroup(4), rest_s=180),
        a_line(SetGroup(3, duration_s=30), rest_s=0),
    ]

    assert session_estimate(lines) == 20


def test_a_session_with_no_lines_has_no_estimate() -> None:
    assert session_estimate([]) is None
