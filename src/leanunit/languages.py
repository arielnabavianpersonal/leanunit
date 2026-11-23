from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leanunit import pycode
from leanunit.pycode import TargetError, split_target

RUNNERS = Path(__file__).parent / "runners"
PYTHON_RUNNER = RUNNERS / "python_runner.py"
NODE_RUNNER = RUNNERS / "node_runner.mjs"
NODE_DESCRIBE = RUNNERS / "node_describe.mjs"
SKIPPED_DIRS = frozenset({".git", ".venv", ".lake", "node_modules", "__pycache__", "dist", "build"})
DESCRIBE_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Language:
    name: str
    suffixes: tuple[str, ...]
    default_runtime: tuple[str, ...]

    def runner_command(self, runtime: tuple[str, ...], source_root: Path) -> list[str]:
        if self.name == "python":
            return [*runtime, str(PYTHON_RUNNER), "--source-root", str(source_root)]
        return [*runtime, str(NODE_RUNNER), "--source-root", str(source_root), "--language", self.name]

    def describe(self, runtime: tuple[str, ...], source_root: Path, cwd: Path, target: str) -> dict[str, Any]:
        split_target(target)
        if self.name == "python":
            command = [*self.runner_command(runtime, source_root), "--describe", target]
        else:
            command = self._node_describe(runtime, source_root, "--describe", target)
        return _run_json(command, cwd)

    def methods_of(self, runtime: tuple[str, ...], source_root: Path, cwd: Path, target: str) -> tuple[str, ...]:
        if self.name == "python":
            return pycode.methods_of(source_root, target)
        answer = _run_json(self._node_describe(runtime, source_root, "--methods", target), cwd)
        return tuple(answer["methods"])

    def module_file(self, source_root: Path, module: str) -> Path:
        if self.name == "python":
            return pycode.module_file(source_root, module)
        for suffix in self.suffixes:
            candidate = source_root / f"{module}{suffix}"
            if candidate.is_file():
                return candidate
        raise TargetError(f"module {module!r} has no {'/'.join(self.suffixes)} file under {source_root}")

    def source_files(self, source_root: Path, skipped: Path) -> list[Path]:
        found = []
        for directory, subdirectories, files in os.walk(source_root):
            current = Path(directory)
            subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_DIRS and current / name != skipped]
            found += [current / name for name in files if name.endswith(self.suffixes)]
        return found

    def _node_describe(self, runtime: tuple[str, ...], source_root: Path, mode: str, target: str) -> list[str]:
        return [*runtime, str(NODE_DESCRIBE), "--source-root", str(source_root), "--language", self.name, mode, target]


PYTHON = Language("python", (".py",), ())
TYPESCRIPT = Language(
    "typescript", (".ts", ".mts", ".cts", ".js", ".mjs"), ("node", "--experimental-strip-types", "--no-warnings")
)
JAVASCRIPT = Language("javascript", (".js", ".mjs", ".cjs"), ("node", "--no-warnings"))
LANGUAGES = {language.name: language for language in (PYTHON, TYPESCRIPT, JAVASCRIPT)}


def _run_json(command: list[str], cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, cwd=cwd, check=False, timeout=DESCRIBE_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TargetError(f"the {Path(command[0]).name} helper did not run: {error}") from error
    lines = completed.stdout.strip().splitlines()
    if completed.returncode != 0 or not lines:
        raise TargetError(f"the language helper failed: {completed.stderr[-2000:]}")
    answer = json.loads(lines[-1])
    if "error" in answer:
        raise TargetError(answer["error"])
    return answer
