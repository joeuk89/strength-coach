from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict[str, object])
