"""A pytest plugin that refuses every network connection and fails any test that tries one.

The failure stands even when the code under test catches the refusal (testing.md: no network in
the suite).
"""

import socket
from collections.abc import Callable, Generator
from typing import Any

import pytest

NETWORK_FAMILIES = {socket.AF_INET, socket.AF_INET6}

_attempts_key = pytest.StashKey[list[str]]()
_originals_key = pytest.StashKey[dict[str, Any]]()


class NetworkRefused(OSError):
    pass


def pytest_configure(config: pytest.Config) -> None:
    attempts: list[str] = []
    config.stash[_attempts_key] = attempts
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    config.stash[_originals_key] = {
        "connect": original_connect,
        "connect_ex": original_connect_ex,
        "getaddrinfo": original_getaddrinfo,
    }

    def refuse(what: str) -> NetworkRefused:
        attempts.append(what)
        return NetworkRefused(f"the test suite refuses network access: {what}")

    def guarded(original: Callable[..., Any]) -> Callable[..., Any]:
        def connect(self: socket.socket, address: Any) -> Any:
            if self.family in NETWORK_FAMILIES:
                raise refuse(f"connect to {address!r}")
            return original(self, address)

        return connect

    def getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        raise refuse(f"resolve {host!r}:{port!r}")

    socket.socket.connect = guarded(original_connect)
    socket.socket.connect_ex = guarded(original_connect_ex)
    socket.getaddrinfo = getaddrinfo


def pytest_unconfigure(config: pytest.Config) -> None:
    originals = config.stash.get(_originals_key, None)
    if originals is None:
        return
    socket.socket.connect = originals["connect"]
    socket.socket.connect_ex = originals["connect_ex"]
    socket.getaddrinfo = originals["getaddrinfo"]


def _guarded_phase(item: pytest.Item) -> Generator[None]:
    attempts = item.config.stash[_attempts_key]
    before = len(attempts)
    try:
        yield
    finally:
        if len(attempts) > before:
            tried = "; ".join(attempts[before:])
            pytest.fail(f"{item.nodeid} opened a network connection: {tried}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None]:
    return (yield from _guarded_phase(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    return (yield from _guarded_phase(item))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None]:
    return (yield from _guarded_phase(item))
