from pathlib import Path

from coach.core.errors import Invalid


def read_draft(path: str) -> bytes:
    """The bytes of a Draft the agent wrote, relative to the working directory (ADR 0002)."""
    try:
        return (Path.cwd() / path).read_bytes()
    except OSError as error:
        raise Invalid(
            "invalid_argument", f"cannot read the Draft {path}: {error.strerror}"
        ) from error
