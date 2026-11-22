from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

LOCKFILE_VERSION = 1


class LockError(Exception):
    pass


@dataclass(frozen=True)
class LawApproval:
    statement: str
    covers: tuple[str, ...]
    approved_by: str
    approved_at: str


@dataclass(frozen=True)
class Lock:
    lean_toolchain: str | None = None
    laws: Mapping[str, LawApproval] = field(default_factory=lambda: MappingProxyType({}))

    def approve(self, name: str, approval: LawApproval) -> Lock:
        return replace(self, laws=MappingProxyType({**self.laws, name: approval}))

    def remove(self, name: str) -> Lock:
        return replace(self, laws=MappingProxyType({key: value for key, value in self.laws.items() if key != name}))

    def with_toolchain(self, toolchain: str) -> Lock:
        return replace(self, lean_toolchain=toolchain)


def load_lock(path: Path) -> Lock:
    if not path.exists():
        return Lock()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise LockError(f"{path} is not valid JSON: {error}") from error
    if data.get("lockfileVersion") != LOCKFILE_VERSION:
        raise LockError(f"{path} has lockfileVersion {data.get('lockfileVersion')!r}, expected {LOCKFILE_VERSION}")
    return Lock(
        lean_toolchain=data.get("leanToolchain"),
        laws=MappingProxyType({name: _parse_approval(entry) for name, entry in data.get("laws", {}).items()}),
    )


def save_lock(path: Path, lock: Lock) -> Path:
    path.write_text(lock_to_json(lock))
    return path


def lock_to_json(lock: Lock) -> str:
    data = {
        "lockfileVersion": LOCKFILE_VERSION,
        "leanToolchain": lock.lean_toolchain,
        "laws": {
            name: {
                "statement": approval.statement,
                "covers": list(approval.covers),
                "approvedBy": approval.approved_by,
                "approvedAt": approval.approved_at,
            }
            for name, approval in lock.laws.items()
        },
    }
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _parse_approval(entry: dict[str, Any]) -> LawApproval:
    return LawApproval(
        statement=entry["statement"],
        covers=tuple(entry.get("covers", [])),
        approved_by=entry["approvedBy"],
        approved_at=entry["approvedAt"],
    )
