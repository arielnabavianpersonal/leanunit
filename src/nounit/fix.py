from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from nounit.approve import AGENT_ENV
from nounit.check import run_check
from nounit.config import CONFIG_FILE, Config
from nounit.report import Owner, Report

AGENT_GUIDE = Path(__file__).parent / "AGENT.md"
DIAGNOSIS_FILE = Path(".nounit") / "diagnosis.md"
LEAN_PROTECTED_FILES = ("lakefile.toml", "lakefile.lean", "lean-toolchain", "lake-manifest.json")
SKIPPED_DIRS = frozenset({".git", ".venv", ".lake", "node_modules", "__pycache__"})


class FixError(Exception):
    pass


@dataclass(frozen=True)
class FixResult:
    started_agent: bool
    agent_exit_code: int | None
    restored: tuple[str, ...]
    before: Report
    after: Report
    diagnosis: str | None


Snapshot = Mapping[Path, bytes | None]


def run_fix(
    config: Config,
    check: Callable[[Config], Report] = run_check,
    spawn: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> FixResult:
    before = check(config)
    if not before.owned_by(Owner.AGENT):
        return FixResult(False, None, (), before, before, None)
    if not config.agent_command:
        raise FixError("Set the agent command in the [agent] table of nounit.toml.")
    diagnosis_path = config.root / DIAGNOSIS_FILE
    diagnosis_path.unlink(missing_ok=True)
    protected = snapshot_protected(config)
    exit_code = _run_agent(config, spawn, build_prompt(config, before))
    restored = restore(protected, _protected_paths(config))
    after = check(config)
    diagnosis = diagnosis_path.read_text() if diagnosis_path.is_file() else None
    return FixResult(True, exit_code, tuple(_relative(config, path) for path in restored), before, after, diagnosis)


def build_prompt(config: Config, report: Report) -> str:
    check_command = f"{sys.executable} -m nounit --root {config.root} check"
    return "\n".join([
        AGENT_GUIDE.read_text(),
        "## This project",
        "",
        f"- Project root: `{config.root}`",
        f"- Lean project: `{config.lean_project}`",
        f"- Code under test, which you must not edit: `{config.source_root}`",
        f"- Check command: `{check_command}`",
        f"- Diagnosis file: `{config.root / DIAGNOSIS_FILE}`",
        "",
        "## The failed check",
        "",
        "```json",
        report.to_json(),
        "```",
        "",
    ])


def snapshot_protected(config: Config) -> Snapshot:
    return MappingProxyType({path: path.read_bytes() for path in _protected_paths(config) if path.is_file()})


def restore(before: Snapshot, after_paths: list[Path]) -> list[Path]:
    restored = []
    for path, content in before.items():
        if not path.is_file() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            restored.append(path)
    for path in after_paths:
        if path not in before and path.is_file():
            path.unlink()
            restored.append(path)
    return sorted(restored)


def _protected_paths(config: Config) -> list[Path]:
    fixed = [config.root / CONFIG_FILE, config.lock_path, *(config.lean_project / name for name in LEAN_PROTECTED_FILES)]
    return sorted({*fixed, *_python_files(config.source_root, config.lean_project)})


def _python_files(source_root: Path, lean_project: Path) -> list[Path]:
    found = []
    for directory, subdirectories, files in os.walk(source_root):
        current = Path(directory)
        subdirectories[:] = [
            name for name in subdirectories if name not in SKIPPED_DIRS and current / name != lean_project
        ]
        found += [current / name for name in files if name.endswith(".py")]
    return found


def _run_agent(config: Config, spawn: Callable[..., subprocess.CompletedProcess], prompt: str) -> int | None:
    try:
        completed = spawn(
            list(config.agent_command),
            input=prompt,
            text=True,
            cwd=config.root,
            env={**os.environ, AGENT_ENV: "1"},
            timeout=config.agent_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None
    except OSError as error:
        raise FixError(f"The agent command did not start: {error}") from error
    return completed.returncode


def _relative(config: Config, path: Path) -> str:
    try:
        return str(path.relative_to(config.root))
    except ValueError:
        return str(path)
