import time
from collections.abc import Callable, Generator

import pytest

LIMIT_S = 1.0

clock_key = pytest.StashKey[Callable[[], float]]()
_elapsed_key = pytest.StashKey[float]()
_reported_key = pytest.StashKey[bool]()
_shared_key = pytest.StashKey[float]()


def _timed(item: pytest.Item) -> Generator[None]:
    clock = item.config.stash.get(clock_key, time.perf_counter)
    start = clock()
    shared_before = item.config.stash.get(_shared_key, 0.0)
    yield
    shared = item.config.stash.get(_shared_key, 0.0) - shared_before
    total = item.stash.get(_elapsed_key, 0.0) + clock() - start - shared
    item.stash[_elapsed_key] = total
    if total > LIMIT_S and not item.stash.get(_reported_key, False):
        item.stash[_reported_key] = True
        pytest.fail(f"{item.nodeid} took {total:.2f} s, over the {LIMIT_S} s budget")


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
) -> Generator[None, object, object]:
    """A module- or session-scoped fixture is setup every test shares, not the cost of the first."""
    if fixturedef.scope == "function":
        return (yield)
    clock = request.config.stash.get(clock_key, time.perf_counter)
    start = clock()
    try:
        return (yield)
    finally:
        spent = clock() - start
        request.config.stash[_shared_key] = request.config.stash.get(_shared_key, 0.0) + spent


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    return (yield from _timed(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    return (yield from _timed(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    return (yield from _timed(item))
