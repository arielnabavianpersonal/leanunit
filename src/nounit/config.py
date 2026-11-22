from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILE = "nounit.toml"
LOCK_FILE = "nounit.lock"
DEFAULT_LEAN_PROJECT = "lean"
DEFAULT_SOURCE_ROOT = "."
DEFAULT_SAMPLES = 300
DEFAULT_SEED = 1
DEFAULT_AGENT_TIMEOUT_SECONDS = 1800


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    root: Path
    lean_project: Path
    python: tuple[str, ...]
    source_root: Path
    cover: tuple[str, ...]
    exclude: tuple[str, ...]
    samples: int
    seed: int
    agent_command: tuple[str, ...]
    agent_timeout_seconds: int

    @property
    def lock_path(self) -> Path:
        return self.root / LOCK_FILE


def load_config(root: Path) -> Config:
    path = root / CONFIG_FILE
    if not path.is_file():
        raise ConfigError(f"{path} does not exist. Run `nounit init` to make it.")
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from error
    python = _section(data, "python")
    lean = _section(data, "lean")
    conformance = _section(data, "conformance")
    agent = _section(data, "agent")
    cover = _targets(python.get("cover", []), "python.cover")
    return Config(
        root=root,
        lean_project=root / lean.get("project", DEFAULT_LEAN_PROJECT),
        python=_command(python.get("interpreter", [sys.executable]), "python.interpreter"),
        source_root=root / python.get("source_root", DEFAULT_SOURCE_ROOT),
        cover=cover,
        exclude=_targets(python.get("exclude", []), "python.exclude"),
        samples=_positive(conformance.get("samples", DEFAULT_SAMPLES), "conformance.samples"),
        seed=int(conformance.get("seed", DEFAULT_SEED)),
        agent_command=_command(agent.get("command", []), "agent.command"),
        agent_timeout_seconds=_positive(
            agent.get("timeout_seconds", DEFAULT_AGENT_TIMEOUT_SECONDS), "agent.timeout_seconds"
        ),
    )


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data.get(name, {})
    if not isinstance(section, dict):
        raise ConfigError(f"[{name}] must be a table")
    return section


def _command(value: Any, key: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ConfigError(f"{key} must be a string or a list of strings")


def _targets(value: Any, key: str) -> tuple[str, ...]:
    targets = _command(value, key) if value else ()
    for target in targets:
        if ":" not in target:
            raise ConfigError(f"{key} entry {target!r} must have the form module:Qualname")
    return targets


def _positive(value: Any, key: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value
