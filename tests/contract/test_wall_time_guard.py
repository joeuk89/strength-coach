import pytest

PLANTED_CONFTEST = """
import pytest
from support.wall_time import clock_key


class FakeClock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds


CLOCK = FakeClock()


def pytest_configure(config):
    config.stash[clock_key] = CLOCK


@pytest.fixture
def fake_clock():
    return CLOCK
"""


def test_a_test_over_one_second_fails(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        def test_slow(fake_clock):
            fake_clock.seconds += 1.5
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*1.50 s*over the 1.0 s budget*"])


def test_a_test_under_one_second_passes(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        def test_quick(fake_clock):
            fake_clock.seconds += 0.5
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(passed=1)


def test_slow_fixture_setup_fails(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def slow(fake_clock):
            fake_clock.seconds += 1.5

        def test_uses_slow(slow):
            pass
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(errors=1)
