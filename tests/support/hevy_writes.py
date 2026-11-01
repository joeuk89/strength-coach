"""A pytest plugin that fails any test whose `FakeHevy` saw a DELETE or a write to
`/v1/workouts*`: no code path may touch the athlete's Hevy history (ADR 0011, "The client")."""

from collections.abc import Generator

import pytest

from support.fake_hevy import RECORDED, Call


def forbidden(call: Call) -> bool:
    method, path = call
    return method == "DELETE" or (method != "GET" and path.startswith("/v1/workouts"))


def _guarded_phase(item: pytest.Item) -> Generator[None]:
    before = len(RECORDED)
    try:
        yield
    finally:
        sent = [f"{m} {p}" for m, p in RECORDED[before:] if forbidden((m, p))]
        if sent:
            pytest.fail(f"{item.nodeid} sent a forbidden Hevy request: {'; '.join(sent)}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    return (yield from _guarded_phase(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    return (yield from _guarded_phase(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    return (yield from _guarded_phase(item))
