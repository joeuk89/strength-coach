import io
import json
from dataclasses import dataclass
from typing import Any

from coach.cli.app import main
from coach.cli.declaration import MakeClient, MakeGitHub
from coach.core.clock import Clock
from support.fake_github import FakeGitHub


@dataclass(frozen=True)
class Run:
    code: int
    stdout: str
    stderr: str

    @property
    def envelope(self) -> Any:
        return json.loads(self.stdout)


def run_coach(
    *argv: str,
    stdout: io.StringIO | None = None,
    env: dict[str, str] | None = None,
    clock: Clock | None = None,
    make_client: MakeClient | None = None,
    make_github: MakeGitHub | None = None,
) -> Run:
    """`coach <argv>` in process. GitHub is always a fake, an empty one unless `make_github`."""
    out = stdout if stdout is not None else io.StringIO()
    err = io.StringIO()
    clients: dict[str, Any] = {"make_github": make_github or FakeGitHub().factory()}
    if make_client is not None:
        clients["make_client"] = make_client
    code = main(list(argv), env or {}, out, err, clock=clock, **clients)
    return Run(code, out.getvalue(), err.getvalue())
