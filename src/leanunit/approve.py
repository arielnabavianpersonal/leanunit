from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from leanunit.check import LeanBackend
from leanunit.config import Config
from leanunit.lean import LawInfo, LeanProject
from leanunit.lock import LawApproval, Lock, load_lock, save_lock

AGENT_ENV = "LEANUNIT_AGENT"


class ApproveError(Exception):
    pass


@dataclass(frozen=True)
class ApproveResult:
    approved: tuple[str, ...]
    removed: tuple[str, ...]
    lock_path: Path


def run_approve(
    config: Config,
    names: Sequence[str],
    approve_all: bool,
    approver: str,
    today: str,
    lean: LeanBackend | None = None,
    environ: Mapping[str, str] = os.environ,
) -> ApproveResult:
    if environ.get(AGENT_ENV):
        raise ApproveError(f"`leanunit approve` is for humans, and {AGENT_ENV} is set, so an agent started it.")
    if not approve_all and not names:
        raise ApproveError("Name the laws to approve, or use --all.")
    audit = (lean or LeanProject(config.lean_project)).audit()
    current = {law.name: law for law in audit.laws}
    lock = load_lock(config.lock_path)
    chosen, removed = _select(names, approve_all, current, lock)
    blocked = [name for name in chosen if current[name].problem]
    if blocked:
        raise ApproveError(f"These laws have problems and cannot be approved: {', '.join(blocked)}")
    for name in chosen:
        law = current[name]
        lock = lock.approve(
            name, LawApproval(statement=law.statement, covers=law.covers, approved_by=approver, approved_at=today)
        )
    for name in removed:
        lock = lock.remove(name)
    save_lock(config.lock_path, lock.with_toolchain(audit.toolchain))
    return ApproveResult(approved=tuple(chosen), removed=tuple(removed), lock_path=config.lock_path)


def _select(
    names: Sequence[str], approve_all: bool, current: Mapping[str, LawInfo], lock: Lock
) -> tuple[list[str], list[str]]:
    if approve_all:
        return sorted(current), sorted(set(lock.laws) - set(current))
    known = set(current) | set(lock.laws)
    resolved = [_resolve(name, known) for name in names]
    return [name for name in resolved if name in current], [name for name in resolved if name not in current]


def _resolve(name: str, known: set[str]) -> str:
    if name in known:
        return name
    matches = sorted(candidate for candidate in known if candidate.rsplit(".", 1)[-1] == name)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ApproveError(f"{name!r} matches more than one law: {', '.join(matches)}")
    raise ApproveError(f"No law is named {name!r}.")
