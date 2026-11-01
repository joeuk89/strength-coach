import json
import subprocess
import sys


def test_python_m_coach_help_exits_0() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "coach", "--help"], capture_output=True, text=True, check=False
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["ok"] is True
