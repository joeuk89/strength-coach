import socket

import pytest


def test_a_planted_real_request_fails_the_suite(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import urllib.request

        def test_reaches_out():
            urllib.request.urlopen("http://127.0.0.1:9/v1/routines", timeout=1)
        """
    )

    result = pytester.runpytest("-p", "support.no_network")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*opened a network connection*"])


def test_a_swallowed_connection_attempt_still_fails_the_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import socket

        def test_hides_its_connection():
            try:
                socket.create_connection(("127.0.0.1", 9), timeout=1)
            except Exception:
                pass
        """
    )

    result = pytester.runpytest("-p", "support.no_network")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*opened a network connection*"])


def test_a_test_without_network_passes(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_offline():
            assert 1 + 1 == 2
        """
    )

    result = pytester.runpytest("-p", "support.no_network")

    result.assert_outcomes(passed=1)


def test_the_guard_leaves_local_socket_pairs_alone() -> None:
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"x")
        assert right.recv(1) == b"x"
