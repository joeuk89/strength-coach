import re
from collections.abc import Mapping

from coach.core.errors import Setup
from coach.core.flag import Flag, Scope, raise_flag

RELEASE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

# What an athlete must know before upgrading into each major version, keyed by that major.
MIGRATION_NOTES: Mapping[int, str] = {}


def is_release(version: str) -> bool:
    return RELEASE.fullmatch(version) is not None


def release(version: str) -> tuple[int, int, int]:
    found = RELEASE.fullmatch(version)
    if found is None:
        raise ValueError(f"{version!r} is not a release X.Y.Z")
    major, minor, patch = (int(part) for part in found.groups())
    return major, minor, patch


def check_pin(engine_version: str, pin: str, *, upgrading: bool = False) -> Flag | None:
    """Compare the running engine with the instance's pin (ADR 0007: exact match, `.dev` warns).

    `upgrading` is `coach upgrade`'s rule: any release at or after the pin, never a `.dev` build.
    """
    if engine_version == pin:
        return None
    if ".dev" in engine_version:
        if upgrading:
            raise Setup(
                "engine_pin_required",
                f"engine {engine_version} is a development build and upgrade writes the pin; "
                "install a release to upgrade",
            )
        return raise_flag(
            "engine_pin_dev",
            Scope("instance"),
            {"pinned_version": pin, "running_version": engine_version},
            f"engine {engine_version} is a development build running against pin {pin}",
        )
    if upgrading and is_release(engine_version) and is_release(pin):
        if release(engine_version) > release(pin):
            return None
        raise Setup(
            "engine_pin_mismatch",
            f"engine {engine_version} is older than the instance pin {pin}; install engine {pin}",
        )
    raise Setup(
        "engine_pin_mismatch",
        f"engine {engine_version} does not match the instance pin {pin}; "
        f"install engine {pin}, or run `coach upgrade` to move the pin to {engine_version}",
    )


def generated_file_drift(file: str, engine_version: str) -> Flag:
    return raise_flag(
        "generated_file_drift",
        Scope("instance"),
        {"file": file, "engine_version": engine_version},
        f"{file} differs from what engine {engine_version} generates; `coach upgrade` rewrites it",
    )


def notes_between(
    pin: str, engine_version: str, notes: Mapping[int, str] = MIGRATION_NOTES
) -> tuple[str, ...]:
    """The migration notes of every major after the pin's, up to the engine's own."""
    first, last = release(pin)[0] + 1, release(engine_version)[0]
    return tuple(notes[major] for major in range(first, last + 1) if major in notes)
