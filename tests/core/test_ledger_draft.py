import datetime

import pytest

from coach.core.errors import Invalid
from coach.core.ledger_draft import WeighInRecord, parse_ledger_draft


def parse(text: str, verb: str = "record"):
    return parse_ledger_draft(text.encode("utf-8"), verb=verb, file="d.toml")


def test_a_weigh_in_table_becomes_a_weigh_in_record() -> None:
    draft = parse("[[weigh_in]]\ndate = 2026-10-30\nkg = 82.4\n")

    assert draft.records == (WeighInRecord(date=datetime.date(2026, 10, 30), kg=82.4),)


def test_the_draft_hash_is_the_sha256_of_the_file_bytes() -> None:
    draft = parse("")

    assert draft.hash == ("sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_an_unknown_table_is_unknown_key() -> None:
    with pytest.raises(Invalid) as raised:
        parse("[[weigh_ins]]\ndate = 2026-10-30\nkg = 82.4\n")

    assert raised.value.code == "unknown_key"


def test_an_unknown_key_in_a_record_is_unknown_key() -> None:
    with pytest.raises(Invalid) as raised:
        parse("[[weigh_in]]\ndate = 2026-10-30\nkg = 82.4\nkgs = 1\n")

    assert raised.value.code == "unknown_key"
    assert "kgs" in raised.value.message


def test_an_observation_in_a_record_file_is_record_kind_not_allowed() -> None:
    with pytest.raises(Invalid) as raised:
        parse('[[observation]]\ntext = "drift adds volume"\n')

    assert raised.value.code == "record_kind_not_allowed"


def test_a_note_about_a_niggle_key_no_record_carries_is_draft_ref_unresolved() -> None:
    with pytest.raises(Invalid) as raised:
        parse('[[note]]\ndate = 2026-10-30\ntext = "sore"\nabout = "niggle:@x"\n')

    assert raised.value.code == "draft_ref_unresolved"
    assert "niggle:@x" in raised.value.message


def test_a_note_may_cite_an_exercise_the_same_file_declares_by_key() -> None:
    draft = parse(
        '[[exercise]]\nid = "custom_hold"\nkey = "hold"\nhevy_template_id = "T1"\n'
        '[[note]]\ndate = 2026-10-30\ntext = "felt easy"\nabout = "exercise:@hold"\n'
    )

    assert draft.keys() == {"hold": 0}


def test_a_key_used_twice_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        parse(
            '[[weigh_in]]\ndate = 2026-10-30\nkg = 82\nkey = "a"\n'
            '[[weigh_in]]\ndate = 2026-10-31\nkg = 82\nkey = "a"\n'
        )

    assert raised.value.code == "invalid_argument"


def test_a_note_about_a_workout_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        parse('[[note]]\ndate = 2026-10-30\ntext = "x"\nabout = "workout:w-0001"\n')

    assert raised.value.code == "invalid_argument"


def test_a_withdrawing_weigh_in_carries_only_what_it_withdraws() -> None:
    assert parse('[[weigh_in]]\nwithdraws = "wi-0001"\n').records == (
        WeighInRecord(withdraws="wi-0001"),
    )
    with pytest.raises(Invalid) as raised:
        parse('[[weigh_in]]\nwithdraws = "wi-0001"\nkg = 80\n')
    assert raised.value.code == "unknown_key"


def test_a_record_table_written_as_a_single_table_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        parse("[weigh_in]\ndate = 2026-10-30\nkg = 82\n")

    assert raised.value.code == "invalid_argument"


def test_a_missing_required_value_names_the_table_and_the_key() -> None:
    with pytest.raises(Invalid) as raised:
        parse("[[sleep_night]]\nnight = 2026-10-30\n")

    assert "[[sleep_night]] #1" in raised.value.message
    assert "hours" in raised.value.message
