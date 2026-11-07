import json
import tomllib

import pytest

from coach.core.config import (
    Athlete,
    Config,
    Engine,
    GridLocation,
    Hevy,
    ImplementChoice,
    IncrementImplement,
    PlatePoolLocation,
    RackImplement,
    parse_config,
)
from coach.render.instance_files import (
    GITIGNORE,
    claude_md,
    coach_toml,
    settings_json,
    with_pin,
)

ATHLETE = Athlete(
    units="lb",
    bodyweight_units="kg",
    week_starts="sunday",
    timezone="America/New_York",
    available_days=("sunday", "tuesday"),
    session_minutes=45,
    checkin_cadence_days=7,
)


def test_coach_toml_parses_back_to_the_config_it_was_written_from() -> None:
    config = Config(
        engine=Engine("0.3.0"),
        athlete=ATHLETE,
        hevy=Hevy(),
        locations=(
            PlatePoolLocation(
                "home",
                kit="home",
                implements={
                    "barbell": "barbell",
                    "dumbbell": "dumbbell",
                    "kettlebell": "kettlebell",
                    "vest": "vest",
                },
                implement={
                    "barbell": ImplementChoice(hardware="none"),
                    "dumbbell": ImplementChoice(hardware="screw-long", single=True),
                    "kettlebell": ImplementChoice(
                        hardware=("screw-standard", "screw-long", "none")
                    ),
                    "vest": ImplementChoice(),
                },
            ),
            GridLocation(
                "gym",
                implements={"barbell": "bar", "dumbbell": "rack"},
                implement={
                    "bar": IncrementImplement(2.5, base=20, max=180),
                    "rack": RackImplement((4, 6, 12.5)),
                },
            ),
        ),
    )

    assert parse_config(tomllib.loads(coach_toml(config))) == config


def test_coach_toml_without_hevy_has_no_hevy_table() -> None:
    document = tomllib.loads(coach_toml(Config(Engine("0.3.0"), ATHLETE)))

    assert "hevy" not in document
    assert "location" not in document


def test_coach_toml_carries_a_commented_example_location_of_each_kind() -> None:
    text = coach_toml(Config(Engine("0.3.0"), ATHLETE))
    uncommented = "\n".join(
        line.removeprefix("# ") if line.startswith("# ") else "" if line == "#" else line
        for line in text.splitlines()
    )

    config = parse_config(tomllib.loads(uncommented))

    kinds = {type(location) for location in config.locations}
    assert kinds == {PlatePoolLocation, GridLocation}
    assert all(location.implements for location in config.locations)
    home = next(loc for loc in config.locations if isinstance(loc, PlatePoolLocation))
    assert home.implement == {
        "barbell": ImplementChoice(hardware="collar-clamp"),
        "dumbbell": ImplementChoice(hardware="screw-standard"),
    }


def test_coach_toml_writes_a_plate_pool_location_as_implement_choice_tables() -> None:
    home = PlatePoolLocation(
        "home",
        kit="home",
        implements={"barbell": "barbell", "dumbbell": "dumbbell"},
        implement={
            "barbell": ImplementChoice(hardware="collar-clamp"),
            "dumbbell": ImplementChoice(hardware="screw-standard", single=True),
        },
    )

    document = tomllib.loads(coach_toml(Config(Engine("0.3.0"), ATHLETE, locations=(home,))))

    assert document["location"]["home"] == {
        "kind": "plate-pool",
        "kit": "home",
        "implements": {"barbell": "barbell", "dumbbell": "dumbbell"},
        "implement": {
            "barbell": {"hardware": "collar-clamp"},
            "dumbbell": {"hardware": "screw-standard", "single": True},
        },
    }


def test_coach_toml_writes_a_hardware_list_as_a_toml_list() -> None:
    home = PlatePoolLocation(
        "home",
        kit="home",
        implements={"dumbbell": "dumbbell"},
        implement={"dumbbell": ImplementChoice(hardware=("screw-standard", "screw-long"))},
    )

    document = tomllib.loads(coach_toml(Config(Engine("0.3.0"), ATHLETE, locations=(home,))))

    assert document["location"]["home"]["implement"] == {
        "dumbbell": {"hardware": ["screw-standard", "screw-long"]}
    }


def test_the_generated_claude_md_is_under_forty_lines_and_names_the_engine_version() -> None:
    text = claude_md("0.3.0")

    assert len(text.splitlines()) < 40
    assert "0.3.0" in text
    assert "coach --help" in text
    assert "coach schema" in text


def test_the_generated_claude_md_names_how_to_read_a_registry() -> None:
    text = claude_md("0.3.0")

    assert "coach schema --registry <name>" in text
    assert "registry names" in text


def test_the_generated_claude_md_names_the_profile_and_the_drafts_once() -> None:
    text = claude_md("0.3.0")

    assert text.count("profile.md") == 1
    assert text.count(".coach/drafts/") == 1


def test_the_generated_claude_md_names_the_options_that_lift_the_default_cuts() -> None:
    text = claude_md("0.3.0")

    assert "--last <n>" in text
    assert "--full" in text


COACH_VOICE = (
    "Everything written to the athlete is coaching in plain words: what they will do, what"
    " changed and why. Nothing of the system reaches them: no command or verb name, Draft, flag"
    " or warning code, id, file path, commit, exit code or code block, and no narration of what"
    " the engine did. Say what a result means for their training, never what it is called. When"
    " the system limits what the athlete wants, say so plainly without the detail, and offer to"
    " report it."
)


def test_the_generated_claude_md_carries_the_coach_voice_section_after_the_bullets() -> None:
    lines = claude_md("0.3.0").splitlines()

    heading = lines.index("## The coach's voice")
    last_bullet = max(i for i, line in enumerate(lines) if line.startswith("- "))
    closing = next(i for i, line in enumerate(lines) if line.startswith("This file and"))
    assert last_bullet < heading < closing
    paragraph = lines[heading + 1 : lines.index("", heading)]
    assert " ".join(paragraph) == COACH_VOICE


REPORTING = (
    "When the system fails or cannot do what the athlete needs, offer to report it: write the"
    " report as a Draft, run `coach report <draft>`, and tell them in plain words it is written"
    " and waits for their yes; the prompt shows them the exact text. Only a bug or a gap is"
    " reported, never a disagreement with a rule. If it cannot be sent, say so without the detail"
    " and that it is kept; the Draft stays for a later try."
)


def test_the_generated_claude_md_carries_the_reporting_line_after_the_voice_rule() -> None:
    text = claude_md("0.3.0")
    lines = text.splitlines()

    heading = lines.index("## The coach's voice")
    after_rule = lines.index("", heading) + 1
    closing = next(i for i, line in enumerate(lines) if line.startswith("This file and"))
    paragraph = lines[after_rule : lines.index("", after_rule)]
    assert " ".join(paragraph) == REPORTING
    assert after_rule + len(paragraph) < closing
    assert text.count("coach report") == 1


def test_settings_allow_coach_and_ask_on_exactly_the_verbs_handed_in() -> None:
    settings = json.loads(settings_json(["publish", "plan apply"]))

    permissions = settings["permissions"]
    assert permissions["allow"] == ["Bash(coach:*)"]
    assert permissions["ask"] == ["Bash(coach plan apply:*)", "Bash(coach publish:*)"]


def test_settings_deny_every_workouts_call_and_webfetch_to_the_hevy_host() -> None:
    permissions = json.loads(settings_json([]))["permissions"]

    assert permissions["deny"] == [
        "Bash(*api.hevyapp.com/v1/workouts*)",
        "WebFetch(domain:api.hevyapp.com)",
    ]


def test_settings_json_is_the_same_bytes_for_the_same_verbs() -> None:
    assert settings_json(["init", "publish"]) == settings_json(["publish", "init"])


def test_the_gitignore_ignores_the_store_the_key_and_local_settings() -> None:
    assert GITIGNORE.splitlines() == [".coach/", ".env", ".claude/settings.local.json"]


AUTHORED = """# my coach
[athlete]
units = "kg"  # the athlete's own comment

[engine]
# pinned by upgrade
version = "0.3.0"

[location.gym]
version = "not the pin"
"""


def test_with_pin_moves_only_the_engine_version_and_keeps_every_other_byte() -> None:
    moved = with_pin(AUTHORED, "0.4.0")

    assert moved == AUTHORED.replace('version = "0.3.0"', 'version = "0.4.0"')
    assert tomllib.loads(moved)["engine"]["version"] == "0.4.0"
    assert tomllib.loads(moved)["location"]["gym"]["version"] == "not the pin"


def test_with_pin_on_a_file_with_no_engine_version_raises() -> None:
    with pytest.raises(ValueError):
        with_pin('[athlete]\nunits = "kg"\n', "0.4.0")
