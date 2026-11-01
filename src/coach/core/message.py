from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    code: str
    message: str
