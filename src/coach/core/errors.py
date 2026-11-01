from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coach.core.flag import Flag


class CoachError(Exception):
    """`details` ride in the envelope's `error` beside the code and message."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
        *,
        warnings: tuple["Flag", ...] = (),
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.warnings = warnings


class Invalid(CoachError):
    """Data or a check failed."""


class Refused(CoachError):
    """A guard refused a write."""


class Unreachable(CoachError):
    """Hevy could not be reached."""


class Setup(CoachError):
    """The instance or the engine is not set up for this verb to run."""
