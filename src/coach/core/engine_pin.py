from coach.core.errors import Setup
from coach.core.notice import Notice


def check_pin(engine_version: str, pin: str) -> Notice | None:
    """Compare the running engine with the instance's pin (ADR 0007: exact match, `.dev` warns)."""
    if engine_version == pin:
        return None
    if ".dev" in engine_version:
        return Notice(
            "engine_pin_dev",
            f"engine {engine_version} is a development build running against pin {pin}",
        )
    raise Setup(
        "engine_pin_mismatch",
        f"engine {engine_version} does not match the instance pin {pin}; "
        f"install engine {pin}, or run `coach upgrade` to move the pin to {engine_version}",
    )
