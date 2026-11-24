from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from leanunit.check import LeanBackend
from leanunit.config import Config
from leanunit.lean import LawInfo, LeanProject
from leanunit.lock import ExclusionApproval, LawApproval, Lock, load_lock, save_lock

AGENT_ENV = "LEANUNIT_AGENT"


class ApproveError(Exception):
    pass


@dataclass(frozen=True)
class ApproveResult:
    approved: tuple[str, ...]
    removed: tuple[str, ...]
    lock_path: Path
    exclusions: tuple[str, ...] = ()


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
    law_names = [name for name in names if name not in config.exclude]
    exclusions = sorted(config.exclude) if approve_all else [name for name in names if name in config.exclude]
    chosen, removed = _select(law_names, approve_all, current, lock) if approve_all or law_names else ([], [])
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
    lock = _approve_exclusions(lock, exclusions, approver, today)
    if approve_all:
        for target in sorted(set(lock.exclusions) - set(config.exclude)):
            lock = lock.remove_exclusion(target)
    save_lock(config.lock_path, lock.with_toolchain(audit.toolchain))
    return ApproveResult(
        approved=tuple(chosen), removed=tuple(removed), lock_path=config.lock_path, exclusions=tuple(exclusions)
    )


def _approve_exclusions(lock: Lock, targets: Sequence[str], approver: str, today: str) -> Lock:
    for target in targets:
        lock = lock.approve_exclusion(target, ExclusionApproval(approved_by=approver, approved_at=today))
    return lock


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
