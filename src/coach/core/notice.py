from dataclasses import dataclass


@dataclass(frozen=True)
class Notice:
    code: str
    message: str
