"""The answers `init` needs: from a flag, the default under `--defaults`, or asked on a TTY."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from coach.cli.clock import clock_for, machine_timezone
from coach.cli.declaration import ArgValue
from coach.cli.terminal import Terminal
from coach.core.config import (
    DEFAULT_CHECKIN_CADENCE_DAYS,
    WEEKDAYS,
    Athlete,
    athlete_fact,
    parse_athlete,
)
from coach.core.errors import CoachError, Invalid

type Args = Mapping[str, ArgValue]
type Env = Mapping[str, str]


@dataclass(frozen=True)
class Question:
    fact: str
    prompt: str
    default: Callable[[Env], str]
    convert: Callable[[str], object] = str

    @property
    def flag(self) -> str:
        return "--" + self.fact.replace("_", "-")


def _whole_number(text: str) -> object:
    try:
        return int(text)
    except ValueError:
        return text


def _days(text: str) -> object:
    return [day.strip().lower() for day in text.split(",") if day.strip()]


QUESTIONS = (
    Question("units", "Units for loads, kg or lb", lambda _: "kg"),
    Question("bodyweight_units", "Units for bodyweight, kg or lb", lambda _: "kg"),
    Question("week_starts", "The day your training week starts", lambda _: "monday"),
    Question("timezone", "Your timezone, as an IANA name", machine_timezone),
    Question(
        "available_days",
        "The days you can train, comma separated",
        lambda _: ",".join(WEEKDAYS),
        _days,
    ),
    Question("session_minutes", "Minutes in a usual session", lambda _: "60", _whole_number),
    Question(
        "checkin_cadence_days",
        "Days between check-ins",
        lambda _: str(DEFAULT_CHECKIN_CADENCE_DAYS),
        _whole_number,
    ),
)
HEVY_FLAG = "--hevy"


@dataclass(frozen=True)
class HevyAnswer:
    on: bool
    key: str | None


def missing_flags(args: Args) -> list[str]:
    names = [q.flag for q in QUESTIONS if q.fact not in args]
    if "hevy" not in args and "hevy_key" not in args:
        names.append(HEVY_FLAG)
    return names


def athlete(args: Args, *, defaults: bool, terminal: Terminal, env: Env) -> Athlete:
    facts: dict[str, object] = {}
    for question in QUESTIONS:
        given = args.get(question.fact)
        if isinstance(given, str):
            facts[question.fact] = _checked(question, given)
        elif defaults:
            facts[question.fact] = _checked(question, question.default(env))
        else:
            facts[question.fact] = _asked(question, terminal, env)
    return parse_athlete(facts)


def hevy(args: Args, *, defaults: bool, terminal: Terminal) -> HevyAnswer:
    key = args.get("hevy_key")
    given = args.get("hevy")
    on = _yes_no(given, HEVY_FLAG) if isinstance(given, str) else None
    if isinstance(key, str):
        if on is False:
            raise Invalid("invalid_argument", "--hevy-key needs Hevy on; drop --hevy no")
        return HevyAnswer(on=True, key=key)
    if on is not None:
        return HevyAnswer(on=on, key=None)
    if defaults:
        return HevyAnswer(on=False, key=None)
    while True:
        try:
            on = _yes_no(terminal.ask("Do you log workouts in Hevy? yes or no", "no"), "answer")
            break
        except Invalid as error:
            terminal.say(error.message)
    if not on:
        return HevyAnswer(on=False, key=None)
    key = terminal.ask_secret("Your Hevy API key (leave blank to add it to .env later)")
    return HevyAnswer(on=True, key=key or None)


def _checked(question: Question, text: str) -> object:
    try:
        value = athlete_fact(question.fact, question.convert(text))
        if question.fact == "timezone":
            clock_for(str(value))
        return value
    except CoachError as error:
        raise Invalid("invalid_argument", f"{question.flag}: {error.message}") from error


def _asked(question: Question, terminal: Terminal, env: Env) -> object:
    while True:
        try:
            return _checked(question, terminal.ask(question.prompt, question.default(env)))
        except Invalid as error:
            terminal.say(error.message)


def _yes_no(text: str, name: str) -> bool:
    answer = text.strip().lower()
    if answer in ("yes", "y"):
        return True
    if answer in ("no", "n"):
        return False
    raise Invalid("invalid_argument", f"{name} takes yes or no, not {text!r}")
