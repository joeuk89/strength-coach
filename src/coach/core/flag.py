import datetime
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import cast, get_args

from coach.core.errors import Invalid
from coach.core.registries.flags import FLAGS, AcknowledgementSource, ScopeKind, Severity
from coach.core.registries.ledger import Reason

CODE = re.compile(r"[a-z][a-z0-9_]*")
SCOPE_KINDS: tuple[ScopeKind, ...] = get_args(ScopeKind.__value__)
DATED_KINDS: frozenset[ScopeKind] = frozenset({"week", "session", "line"})

# docs/spec/validation.md, "Identity": the refs each scope kind takes, in key order after the
# Monday a dated scope leads with.
REFS: dict[ScopeKind, tuple[str, ...]] = {
    "week": (),
    "session": ("session_id",),
    "line": ("session_id", "exercise_id"),
    "exposure": ("workout_id", "exercise_id"),
    "routine": ("routine_id",),
    "workout": ("workout_id",),
    "instance": (),
    "version": ("version_id",),
    "dose": ("version_id", "target"),
    "priority_lift": ("version_id", "exercise_id"),
    "counted_variant": ("version_id", "lift", "variant"),
    "exercise": ("exercise_id",),
}
REF_FIELDS = (
    "session_id",
    "exercise_id",
    "workout_id",
    "routine_id",
    "version_id",
    "target",
    "lift",
    "variant",
)


@dataclass(frozen=True)
class Scope:
    """The typed target a flag is about. `week` always carries its Monday; `session` and `line`
    carry it on a WeekPlan and drop it in the calendar-free form."""

    kind: ScopeKind
    monday: datetime.date | None = None
    session_id: str | None = None
    exercise_id: str | None = None
    workout_id: str | None = None
    routine_id: str | None = None
    version_id: str | None = None
    target: str | None = None
    lift: str | None = None
    variant: str | None = None

    def __post_init__(self) -> None:
        wanted = REFS[self.kind]
        for name in REF_FIELDS:
            present = getattr(self, name) is not None
            if present != (name in wanted):
                raise ValueError(f"a {self.kind} scope {'has no' if present else 'takes'} {name}")
        if self.kind == "week" and self.monday is None:
            raise ValueError("a week scope takes its Monday")
        if self.kind not in DATED_KINDS and self.monday is not None:
            raise ValueError(f"a {self.kind} scope has no Monday")
        if self.monday is not None and self.monday.weekday() != 0:
            raise ValueError(f"{self.monday} is not a Monday")

    @property
    def dated(self) -> bool:
        return self.monday is not None

    def refs(self) -> tuple[str, ...]:
        named = tuple(str(getattr(self, name)) for name in REFS[self.kind])
        return (self.monday.isoformat(), *named) if self.monday else named

    def calendar_free(self) -> "Scope":
        if self.kind == "week":
            raise Invalid("invalid_argument", "a week scope has no calendar-free form")
        return replace(self, monday=None)

    def to_json(self) -> dict[str, object]:
        document: dict[str, object] = {"kind": self.kind}
        if self.monday:
            document["week"] = self.monday.isoformat()
        for name in REFS[self.kind]:
            document[name.removesuffix("_id")] = getattr(self, name)
        return document


@dataclass(frozen=True)
class FlagKey:
    """`code@<scope kind>:<refs joined by />`, or `code@<scope kind>` when the scope has no ref."""

    code: str
    scope: Scope

    def __str__(self) -> str:
        refs = self.scope.refs()
        tail = f":{'/'.join(refs)}" if refs else ""
        return f"{self.code}@{self.scope.kind}{tail}"

    @classmethod
    def parse(cls, text: str) -> "FlagKey":
        code, at, rest = text.partition("@")
        kind, colon, joined = rest.partition(":")
        if not at or not CODE.fullmatch(code) or kind not in SCOPE_KINDS:
            raise Invalid("invalid_argument", f"{text!r} is not a flag key")
        parts = joined.split("/") if colon else []
        names = REFS[kind]
        monday = None
        if kind in DATED_KINDS and len(parts) == len(names) + 1:
            monday = _monday(parts.pop(0), text)
        if len(parts) != len(names) or not all(parts):
            raise Invalid("invalid_argument", f"{text!r} has the wrong refs for a {kind} scope")
        try:
            scope = Scope(kind, monday, **dict(zip(names, parts, strict=True)))
        except ValueError as error:
            raise Invalid("invalid_argument", f"{text!r}: {error}") from error
        return cls(code, scope)

    def calendar_free(self) -> "FlagKey":
        return FlagKey(self.code, self.scope.calendar_free())


def _monday(text: str, key: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as error:
        raise Invalid("invalid_argument", f"{key!r}: {text!r} is not a date") from error


@dataclass(frozen=True)
class Left:
    because: Reason
    text: str
    source: AcknowledgementSource
    evidence: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "because": self.because,
            "text": self.text,
            "source": self.source,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class Flag:
    code: str
    severity: Severity
    scope: Scope
    params: Mapping[str, object]
    rn: str | None
    message: str
    left: Left | None = None

    def __post_init__(self) -> None:
        if self.severity == "violation" and self.left is not None:
            raise ValueError("a violation is never left")

    @property
    def key(self) -> str:
        return str(FlagKey(self.code, self.scope))

    @property
    def params_hash(self) -> str:
        hashed = (
            FLAGS.get(self.code).hashed_params(self.params) if self.code in FLAGS else self.params
        )
        canonical = json.dumps(hashed, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_json(self) -> dict[str, object]:
        return {
            "key": self.key,
            "code": self.code,
            "severity": self.severity,
            "scope": self.scope.to_json(),
            "params": dict(self.params),
            "params_hash": self.params_hash,
            "rn": self.rn,
            "message": self.message,
            "left": self.left.to_json() if self.left else None,
        }

    @classmethod
    def from_json(cls, document: Mapping[str, object]) -> "Flag":
        """A flag as `to_json` wrote it, such as one frozen on a prescription row."""
        key = FlagKey.parse(str(document["key"]))
        left = document.get("left")
        rn = document.get("rn")
        return cls(
            key.code,
            cast(Severity, document["severity"]),
            key.scope,
            cast(Mapping[str, object], document["params"]),
            None if rn is None else str(rn),
            str(document["message"]),
            None if left is None else _left(cast(Mapping[str, object], left)),
        )

    def to_summary(self) -> dict[str, object]:
        """The flag in a default summary: its key, its params hash and what it says, the params
        left out."""
        return {
            "key": self.key,
            "params_hash": self.params_hash,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "left": self.left.to_json() if self.left else None,
        }


def grouped(flags: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Flags as `Flag.to_json` writes them, one row per code in the order each code first appears:
    its severity, count and keys, each key with the params hash an acknowledgement copies."""
    by_code: dict[object, list[Mapping[str, object]]] = {}
    for flag in flags:
        by_code.setdefault(flag["code"], []).append(flag)
    return [
        {
            "code": code,
            "severity": found[0]["severity"],
            "count": len(found),
            "keys": [{"key": f["key"], "params_hash": f["params_hash"]} for f in found],
        }
        for code, found in by_code.items()
    ]


def _left(document: Mapping[str, object]) -> Left:
    return Left(
        cast(Reason, document["because"]),
        str(document["text"]),
        cast(AcknowledgementSource, document["source"]),
        tuple(str(ref) for ref in cast(list[object], document["evidence"])),
    )


def raise_flag(
    code: str, scope: Scope, params: Mapping[str, object], message: str, *, rn: str | None = None
) -> Flag:
    """A flag at its registry row's severity, on a scope and with params the row names, citing
    the row's ref (or, where the row rests on several, the one passed)."""
    row = FLAGS.get(code)
    if scope.kind not in row.scopes:
        raise ValueError(f"{code} is not raised on a {scope.kind} scope")
    unknown = set(params) - set(row.params)
    if unknown:
        raise ValueError(f"{code} has no params {sorted(unknown)}")
    refs = row.refs_for(params)
    if rn is None:
        if len(refs) > 1:
            raise ValueError(f"{code} rests on {list(refs)}; pass the rn that raised it")
        rn = refs[0] if refs else None
    elif rn not in refs:
        raise ValueError(f"{code} does not cite rn {rn!r}")
    return Flag(code, row.severity, scope, dict(params), rn, message)


@dataclass(frozen=True)
class Acknowledgement:
    """The coach's typed reason for leaving a warning. On a WeekPlan it names the dated key, on a
    program version the version's own key; on a `leave_warning` Decision it names the
    calendar-free key, so it outlasts the week."""

    key: FlagKey
    params_hash: str
    because: Reason
    text: str
    evidence: tuple[str, ...] = ()
    source: AcknowledgementSource = "weekplan"

    def __post_init__(self) -> None:
        if self.source == "decision":
            if self.key.scope.kind == "week":
                raise Invalid(
                    "invalid_argument", f"a Decision cannot leave {self.key}: a week scope"
                )
            if self.key.scope.dated:
                raise Invalid(
                    "invalid_argument", f"a Decision names the calendar-free key, not {self.key}"
                )

    def binds(self, flag: Flag) -> bool:
        if self.source not in FLAGS.get(flag.code).left_by:
            return False
        if flag.params_hash != self.params_hash:
            return False
        key = FlagKey(flag.code, flag.scope)
        if self.source != "decision":
            return key == self.key
        return flag.scope.kind != "week" and key.calendar_free() == self.key


def leave(flag: Flag, acknowledgements: Iterable[Acknowledgement]) -> Flag:
    for acknowledgement in acknowledgements:
        if acknowledgement.binds(flag):
            left = Left(
                acknowledgement.because,
                acknowledgement.text,
                acknowledgement.source,
                acknowledgement.evidence,
            )
            return replace(flag, left=left)
    return flag
