import io
import json
from dataclasses import dataclass
from typing import Any

from coach.cli.app import main
from coach.cli.declaration import MakeClient
from coach.core.clock import Clock


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
) -> Run:
    out = stdout if stdout is not None else io.StringIO()
    err = io.StringIO()
    if make_client is None:
        code = main(list(argv), env or {}, out, err, clock=clock)
    else:
        code = main(list(argv), env or {}, out, err, clock=clock, make_client=make_client)
    return Run(code, out.getvalue(), err.getvalue())
