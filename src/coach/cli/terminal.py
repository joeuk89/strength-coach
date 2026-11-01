import getpass
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class Terminal:
    """The human at a TTY. Questions go to stderr, so stdout stays one JSON document."""

    stdin: TextIO
    out: TextIO

    @property
    def interactive(self) -> bool:
        return self.stdin.isatty()

    def say(self, text: str) -> None:
        self.out.write(text + "\n")
        self.out.flush()

    def ask(self, question: str, default: str | None = None) -> str:
        self.out.write(f"{question} [{default}]: " if default is not None else f"{question}: ")
        self.out.flush()
        answer = self.stdin.readline().strip()
        return answer if answer or default is None else default

    def ask_secret(self, question: str) -> str:
        if _is_real_tty(self.stdin):
            return getpass.getpass(f"{question}: ", stream=self.out).strip()
        return self.ask(question, "")

    def confirm(self, question: str) -> bool:
        return self.ask(f"{question} [y/N]").lower() in ("y", "yes")


def _is_real_tty(stream: TextIO) -> bool:
    try:
        stream.fileno()
    except (OSError, ValueError):
        return False
    return stream.isatty()
