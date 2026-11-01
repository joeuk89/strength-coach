import time
from collections.abc import Callable, Generator

import pytest

LIMIT_S = 1.0

clock_key = pytest.StashKey[Callable[[], float]]()


def _timed(item: pytest.Item) -> Generator[None]:
    clock = item.config.stash.get(clock_key, time.perf_counter)
    start = clock()
    yield
    elapsed = clock() - start
    if elapsed > LIMIT_S:
        pytest.fail(f"{item.nodeid} took {elapsed:.2f} s, over the {LIMIT_S} s budget")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    return (yield from _timed(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    return (yield from _timed(item))
