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


@pytest.fixture(autouse=True)
def off_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)


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


def test_setup_and_body_together_over_one_second_fail(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def slowish(fake_clock):
            fake_clock.seconds += 0.6

        def test_uses_slowish(slowish, fake_clock):
            fake_clock.seconds += 0.6
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*1.20 s*over the 1.0 s budget*"])


def test_slow_teardown_counts_once_toward_the_budget(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def slow_teardown(fake_clock):
            yield
            fake_clock.seconds += 0.6

        def test_uses_slow_teardown(slow_teardown, fake_clock):
            fake_clock.seconds += 0.6
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*1.20 s*over the 1.0 s budget*"])


def test_a_shared_fixture_does_not_count_toward_the_first_test_that_uses_it(
    pytester: pytest.Pytester,
) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        import pytest
        from conftest import CLOCK

        @pytest.fixture(scope="module")
        def shared():
            CLOCK.seconds += 1.5

        def test_first(shared, fake_clock):
            fake_clock.seconds += 0.6

        def test_second(shared):
            pass
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(passed=2)


def test_a_slow_test_using_a_shared_fixture_still_fails(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        import pytest
        from conftest import CLOCK

        @pytest.fixture(scope="module")
        def shared():
            CLOCK.seconds += 0.5

        def test_slow(shared, fake_clock):
            fake_clock.seconds += 1.5
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*1.50 s*over the 1.0 s budget*"])


def test_on_ci_a_test_over_one_second_and_under_three_passes(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        def test_slowish(fake_clock):
            fake_clock.seconds += 2.5
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(passed=1)


def test_on_ci_a_test_over_three_seconds_fails(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    pytester.makeconftest(PLANTED_CONFTEST)
    pytester.makepyfile(
        """
        def test_slow(fake_clock):
            fake_clock.seconds += 3.5
        """
    )

    result = pytester.runpytest("-p", "support.wall_time")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*3.50 s*over the 3.0 s budget*"])
