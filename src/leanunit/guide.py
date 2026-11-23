from __future__ import annotations

from pathlib import Path

GUIDE = Path(__file__).parent / "GUIDE.md"
GUIDE_FILE = "LEANUNIT.md"
POINTER = (
    "## LeanUnit\n\n"
    f"This project uses LeanUnit. Read `{GUIDE_FILE}` before you change code that `leanunit.toml` covers.\n"
)
AGENT_FILES = (("AGENTS.md", True), ("CLAUDE.md", False))


def guide_text() -> str:
    return GUIDE.read_text()


def write_guide(root: Path) -> tuple[Path, ...]:
    written = []
    guide_path = root / GUIDE_FILE
    text = guide_text()
    if not guide_path.is_file() or guide_path.read_text() != text:
        guide_path.write_text(text)
        written.append(guide_path)
    for file_name, create in AGENT_FILES:
        path = root / file_name
        if _add_pointer(path, create):
            written.append(path)
    return tuple(written)


def _add_pointer(path: Path, create: bool) -> bool:
    if not path.is_file() and not create:
        return False
    text = path.read_text() if path.is_file() else ""
    if GUIDE_FILE in text:
        return False
    separator = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    path.write_text(text + separator + POINTER)
    return True
