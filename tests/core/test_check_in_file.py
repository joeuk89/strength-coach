import datetime

import pytest

from coach.core.check_in_file import CheckInFile, parse_check_in_file
from coach.core.errors import Invalid
from coach.core.goal import PhaseClose, PhaseOpen, Until
from coach.core.ledger_draft import ObservationRecord, WeighInRecord
from coach.core.ref import Ref

HEADER = 'date = 2026-11-01\ntier = "light"\nread = "a steady week"\n'


def parse(text: str) -> CheckInFile:
    return parse_check_in_file(text.encode("utf-8"), file="ci.toml")


def test_the_header_and_the_records_are_read_apart() -> None:
    checkin = parse(
        HEADER + 'readiness = "good"\nwindow_start = 2026-10-26\n'
        "[[weigh_in]]\ndate = 2026-11-01\nkg = 82.4\n"
    )

    assert checkin.date == datetime.date(2026, 11, 1)
    assert (checkin.tier, checkin.read, checkin.readiness) == ("light", "a steady week", "good")
    assert checkin.window_start == datetime.date(2026, 10, 26)
    assert checkin.draft.records == (WeighInRecord(date=datetime.date(2026, 11, 1), kg=82.4),)
    assert checkin.draft.hash.startswith("sha256:")


@pytest.mark.parametrize("missing", ["date", "tier", "read"])
def test_the_header_requires_date_tier_and_read(missing: str) -> None:
    text = "".join(line + "\n" for line in HEADER.splitlines() if not line.startswith(missing))

    with pytest.raises(Invalid) as raised:
        parse(text)

    assert missing in raised.value.message


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('tier = "light"', 'tier = "medium"'),
        ('tier = "light"', 'tier = "light"\nreadiness = "great"'),
        ('tier = "light"', 'tier = "light"\ncolour = "red"'),
    ],
)
def test_a_bad_header_value_is_refused(old: str, new: str) -> None:
    with pytest.raises(Invalid):
        parse(HEADER.replace(old, new))


def test_an_observation_is_raised_with_evidence_or_retired_with_a_reason() -> None:
    checkin = parse(
        HEADER + '[[niggle]]\nkey = "ham"\nsite = "hamstring"\ndate = 2026-11-01\n'
        'status = "reported"\n'
        '[[observation]]\ntext = "drift adds volume"\nevidence = ["niggle:@ham"]\n'
        '[[observation]]\nretire = "o-0002"\nbecause = "no longer holds"\n'
    )

    assert checkin.draft.records[1:] == (
        ObservationRecord(text="drift adds volume", evidence=(Ref("niggle", "@ham"),)),
        ObservationRecord(retire="o-0002", because="no longer holds"),
    )


@pytest.mark.parametrize(
    "table",
    [
        '[[observation]]\nevidence = ["niggle:n-0001"]\n',
        '[[observation]]\nretire = "o-0002"\n',
        '[[observation]]\nretire = "o-0002"\nbecause = "gone"\ntext = "x"\n',
        '[[observation]]\nretire = "d-0002"\nbecause = "gone"\n',
        '[[observation]]\ntext = "x"\nevidence = ["niggle:@nobody"]\n',
    ],
)
def test_a_malformed_observation_is_refused(table: str) -> None:
    with pytest.raises(Invalid):
        parse(HEADER + table)


def test_a_phase_opens_with_the_kinds_default_rate() -> None:
    checkin = parse(
        HEADER + '[phase]\nkind = "deficit"\nuntil = { kind = "coachs_call" }\n'
        'because = "cut for summer"\n'
    )

    assert checkin.phase == PhaseOpen(
        kind="deficit",
        rate_pct_bw_per_week=-0.5,
        until=Until("coachs_call"),
        because="cut for summer",
    )


def test_a_phase_closes_with_a_reason() -> None:
    checkin = parse(HEADER + '[phase]\nclose = true\nbecause = "reached the weight"\n')

    assert checkin.phase == PhaseClose("reached the weight")


@pytest.mark.parametrize(
    "table",
    [
        "[phase]\nclose = true\n",
        '[phase]\nclose = false\nbecause = "x"\n',
        '[phase]\nclose = true\nbecause = "x"\nkind = "deficit"\n',
        '[phase]\nkind = "deficit"\nbecause = "x"\n',
    ],
)
def test_a_malformed_phase_is_refused(table: str) -> None:
    with pytest.raises(Invalid):
        parse(HEADER + table)
