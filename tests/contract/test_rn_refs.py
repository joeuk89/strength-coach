from pathlib import Path

from support.rn_refs import problems, refs_in_registries, refs_in_source

REPO = Path(__file__).resolve().parents[2]
NOTES = REPO / "docs" / "spec"

CLAIMS_NOTE = """<!-- coach:note
id = "naps"

[[claims]]
n = 1
text = "Naps help."
status = "current"

[[claims]]
n = 2
text = "Naps help a lot."
status = "retired"
-->

# Naps
"""

PROSE_NOTE = "# Rest\n\n## 1. Between sets\n\nText.\n\n## 2. Between sessions\n"


def test_every_rn_in_the_registries_and_the_source_resolves() -> None:
    # The second permitted read of spec documents (docs/spec/testing.md, "Two explicit
    # exceptions"): headings and claim numbers only.
    refs = refs_in_registries() | refs_in_source(REPO / "src")

    assert "rn:progression-methods §4" in refs
    assert "rn:detraining-return.3" in refs
    assert problems(refs, NOTES) == []


def test_a_claim_that_does_not_exist_fails() -> None:
    assert problems(["rn:deloads.99"], NOTES) == ["rn:deloads.99: deloads.md has no claim 99"]


def test_a_retired_claim_fails(tmp_path: Path) -> None:
    (tmp_path / "naps.md").write_text(CLAIMS_NOTE, encoding="utf-8")

    assert problems(["rn:naps.1", "rn:naps.2"], tmp_path) == ["rn:naps.2: claim 2 is retired"]


def test_a_section_resolves_by_its_numbered_heading(tmp_path: Path) -> None:
    (tmp_path / "rest.md").write_text(PROSE_NOTE, encoding="utf-8")

    assert problems(["rn:rest §2", "rn:rest §3"], tmp_path) == ["rn:rest §3: no section 3"]


def test_a_ref_to_a_missing_note_or_in_neither_form_fails(tmp_path: Path) -> None:
    assert problems(["rn:sleep.1", "rn:sleep"], tmp_path) == [
        "rn:sleep: not rn:<note>.<n> or rn:<note> §<n>",
        "rn:sleep.1: no note sleep.md",
    ]


def test_a_planted_ref_in_the_source_is_found(tmp_path: Path) -> None:
    (tmp_path / "coach").mkdir()
    (tmp_path / "coach" / "rule.py").write_text('RN = "rn:deloads.99"\n', encoding="utf-8")

    refs = refs_in_source(tmp_path)

    assert refs == {"rn:deloads.99"}
    assert problems(refs, NOTES) == ["rn:deloads.99: deloads.md has no claim 99"]
