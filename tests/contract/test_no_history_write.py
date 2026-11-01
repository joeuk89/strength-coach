import pytest
from support.fake_hevy import RECORDED

PLANTED = """
from support.clock import FixedClock
from support.fake_hevy import RECORDED, FakeHevy

def test_planted():
    hevy = FakeHevy(FixedClock())
    hevy.routines()
    RECORDED.append(({method!r}, {path!r}))
"""


def run_planted(pytester: pytest.Pytester, method: str, path: str) -> pytest.RunResult:
    """The inner run shares this process's record, so what it planted is dropped before this
    test's own guard reads it."""
    pytester.makepyfile(PLANTED.format(method=method, path=path))
    before = len(RECORDED)
    try:
        return pytester.runpytest("-p", "support.hevy_writes", "-p", "no:xdist")
    finally:
        del RECORDED[before:]


@pytest.mark.parametrize(
    ("method", "path"),
    [("DELETE", "/v1/routines/r-1"), ("POST", "/v1/workouts"), ("PUT", "/v1/workouts/w-1")],
)
def test_a_delete_or_a_workout_write_through_the_fake_fails_the_suite(
    pytester: pytest.Pytester, method: str, path: str
) -> None:
    result = run_planted(pytester, method, path)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*sent a forbidden Hevy request*"])


def test_reads_and_routine_writes_pass(pytester: pytest.Pytester) -> None:
    result = run_planted(pytester, "PUT", "/v1/routines/r-1")

    result.assert_outcomes(passed=1)
