import io


class TerminalInput(io.StringIO):
    """Stdin as an interactive terminal: the athlete's typed answers, one per line."""

    def isatty(self) -> bool:
        return True


def typed(*answers: str) -> TerminalInput:
    return TerminalInput("".join(f"{answer}\n" for answer in answers))
