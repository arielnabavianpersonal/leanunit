from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nounit.config import CONFIG_FILE, DEFAULT_LEAN_PROJECT, LOCK_FILE
from nounit.lock import Lock, lock_to_json

NOUNIT_LEAN = Path(__file__).parent / "lean"
LEAN_DIRS = ("Laws", "Model", "Proofs", "Gen")
IGNORED = (f"{DEFAULT_LEAN_PROJECT}/.lake/", f"{DEFAULT_LEAN_PROJECT}/NoUnitGenerated/", ".nounit/")


class InitError(Exception):
    pass


@dataclass(frozen=True)
class InitResult:
    created: tuple[Path, ...]


def init_project(root: Path, source_root: str, cover: tuple[str, ...]) -> InitResult:
    lean = root / DEFAULT_LEAN_PROJECT
    existing = [path for path in (root / CONFIG_FILE, root / LOCK_FILE, lean) if path.exists()]
    if existing:
        raise InitError(f"NoUnit does not overwrite files. These already exist: {', '.join(map(str, existing))}")
    files = {
        root / CONFIG_FILE: _config_text(source_root, cover),
        root / LOCK_FILE: lock_to_json(Lock()),
        lean / "lakefile.toml": _lakefile_text(root.name),
        lean / "lean-toolchain": (NOUNIT_LEAN / "lean-toolchain").read_text(),
        **{lean / directory / ".gitkeep": "" for directory in LEAN_DIRS},
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    gitignore = _extend_gitignore(root / ".gitignore")
    return InitResult(created=(*files, *gitignore))


def _config_text(source_root: str, cover: tuple[str, ...]) -> str:
    targets = ", ".join(f'"{target}"' for target in cover)
    return "\n".join([
        "[python]",
        f'source_root = "{source_root}"',
        f"cover = [{targets}]",
        "exclude = []",
        "",
        "[lean]",
        f'project = "{DEFAULT_LEAN_PROJECT}"',
        "",
        "[conformance]",
        "samples = 300",
        "seed = 1",
        "",
        "[agent]",
        "command = []",
        "",
    ])


def _lakefile_text(project_name: str) -> str:
    package = "".join(char if char.isalnum() else "_" for char in project_name) or "project"
    return "\n".join([
        f'name = "{package}_spec"',
        'defaultTargets = ["Spec"]',
        "",
        "[[require]]",
        'name = "NoUnit"',
        f'path = "{NOUNIT_LEAN}"',
        "",
        "[[lean_lib]]",
        'name = "Spec"',
        'globs = ["Laws.+", "Model.+", "Proofs.+", "Gen.+"]',
        "",
    ])


def _extend_gitignore(path: Path) -> tuple[Path, ...]:
    text = path.read_text() if path.is_file() else ""
    missing = [entry for entry in IGNORED if entry not in text.splitlines()]
    if not missing:
        return ()
    prefix = "\n" if text and not text.endswith("\n") else ""
    with path.open("a") as handle:
        handle.write(prefix + "\n".join(missing) + "\n")
    return (path,)
