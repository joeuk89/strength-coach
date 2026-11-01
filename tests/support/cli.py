import io
import json
from dataclasses import dataclass
from typing import Any

from coach.cli.app import main


@dataclass(frozen=True)
class Run:
    code: int
    stdout: str
    stderr: str

    @property
    def envelope(self) -> Any:
        return json.loads(self.stdout)


def run_coach(*argv: str, stdout: io.StringIO | None = None) -> Run:
    out = stdout if stdout is not None else io.StringIO()
    err = io.StringIO()
    code = main(list(argv), {}, out, err)
    return Run(code, out.getvalue(), err.getvalue())
