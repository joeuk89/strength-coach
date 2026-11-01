import re
from dataclasses import dataclass

from coach.core.errors import Invalid

# docs/spec/schema.md, "Refs": the one ref grammar.
REF_KINDS = (
    "planned_session",
    "exposure",
    "workout",
    "block",
    "check_in",
    "exercise",
    "niggle",
    "follow_up",
    "decision",
    "goal",
    "routine",
    "milestone",
    "phase",
    "rn",
)
LOCAL = "@"
KEY = re.compile(r"[A-Za-z0-9_-]+")
# A ref kind names its record kind, except where the two spellings differ.
RECORD_KIND_OF = {"follow_up": "followup"}


@dataclass(frozen=True)
class Ref:
    """`kind:id`, or `kind:@key` citing a record the same Draft raises under `key`."""

    kind: str
    id: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"

    @property
    def local_key(self) -> str | None:
        return self.id.removeprefix(LOCAL) if self.id.startswith(LOCAL) else None

    @property
    def record_kind(self) -> str:
        return RECORD_KIND_OF.get(self.kind, self.kind)

    @classmethod
    def parse(cls, text: str) -> "Ref":
        kind, colon, id_ = text.partition(":")
        if not colon or kind not in REF_KINDS or not id_:
            raise Invalid("invalid_argument", f"{text!r} is not a ref (`kind:id`, schema.md)")
        ref = cls(kind, id_)
        local = ref.local_key
        if local is not None and not KEY.fullmatch(local):
            raise Invalid("invalid_argument", f"{text!r} cites {local!r}, which is not a key")
        return ref

    def resolved(self, id_: str) -> "Ref":
        return Ref(self.kind, id_)
