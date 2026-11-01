import contextlib
import io
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from coach.cli.app import main

type Envelope = dict[str, Any]
type CoachRun = Callable[[Sequence[str], Path], Envelope]


def run_in_process(argv: Sequence[str], cwd: Path) -> Envelope:
    """The verb's envelope from `coach <argv>` run here, in `cwd`, as the command would run."""
    stdout = io.StringIO()
    with contextlib.chdir(cwd):
        main(list(argv), os.environ, stdout, io.StringIO())
    return json.loads(stdout.getvalue())
