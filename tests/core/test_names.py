from coach.core.names import named

NAMES = {"bb_bench_press": "Bench Press (Barbell)"}


def test_an_id_with_a_name_reads_as_its_name() -> None:
    assert named(NAMES, "bb_bench_press") == "Bench Press (Barbell)"


def test_an_id_with_no_name_stands_for_itself() -> None:
    assert named(NAMES, "db_row") == "db_row"
