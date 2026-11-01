from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coach.core.flag import Flag


class CoachError(Exception):
    def __init__(self, code: str, message: str, *, warnings: tuple["Flag", ...] = ()) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.warnings = warnings


class Invalid(CoachError):
    """Data or a check failed."""


class Refused(CoachError):
    """A guard refused a write."""


class Unreachable(CoachError):
    """Hevy could not be reached."""


class Setup(CoachError):
    """The instance or the engine is not set up for this verb to run."""
