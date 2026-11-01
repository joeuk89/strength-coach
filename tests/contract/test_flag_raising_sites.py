from pathlib import Path

from support.raising_sites import unraised

from coach.core.registries.flags import FLAGS

SRC = Path(__file__).resolve().parents[2] / "src"

# A registry code no engine code raises yet, with the reason it stands.
UNRAISED: dict[str, str] = {}


def test_every_registry_flag_has_a_raising_site_or_a_stated_reason() -> None:
    codes = [code.name for code in FLAGS.entries]

    assert unraised(SRC, codes) == sorted(UNRAISED)


def plant(root: Path, module: str, source: str) -> None:
    path = root / "coach" / Path(*module.split(".")).with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_a_code_named_only_in_the_registry_has_no_raising_site(tmp_path: Path) -> None:
    plant(tmp_path, "core.registries.flags", 'CODES = ("stall_streak", "no_e1rm")\n')
    plant(tmp_path, "core.stall", 'def f(raise_flag):\n    return raise_flag("stall_streak")\n')

    assert unraised(tmp_path, ["stall_streak", "no_e1rm"]) == ["no_e1rm"]
