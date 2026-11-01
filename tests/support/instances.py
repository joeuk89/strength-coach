from pathlib import Path


def an_instance(root: Path, *, pin: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "coach.toml").write_text(f'[engine]\nversion = "{pin}"\n', encoding="utf-8")
    return root
