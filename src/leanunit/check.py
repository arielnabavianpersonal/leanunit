from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from leanunit.config import Config
from leanunit.conformance import ConformanceResult, run_conformance
from leanunit.lean import Audit, LawInfo, LeanError, LeanProject, Sample
from leanunit.lock import Lock, load_lock
from leanunit.pycode import TargetError, methods_of, module_file, split_target
from leanunit.report import Finding, FindingKind, LawState, LawStatus, Report, TargetCoverage, TargetStatus

ALLOWED_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
LOG_TAIL_CHARS = 6000


class LeanBackend(Protocol):
    def audit(self) -> Audit: ...

    def sample(self, audit: Audit, count: int, seed: int) -> tuple[Sample, ...]: ...


def run_check(config: Config, lean: LeanBackend | None = None) -> Report:
    backend = lean or LeanProject(config.lean_project)
    lock = load_lock(config.lock_path)
    try:
        audit = backend.audit()
    except LeanError as error:
        return Report(findings=(_lean_error(error),))
    targets = _cover_targets(config)
    findings = [*_law_findings(audit, lock), *_forbidden_findings(audit), *_coverage_findings(targets, audit)]
    try:
        samples = backend.sample(audit, config.samples, config.seed)
    except LeanError as error:
        findings.append(_lean_error(error))
        samples = ()
    conformance = run_conformance(config, samples)
    findings += _conformance_findings(config, conformance)
    return Report(
        findings=tuple(findings),
        laws=_law_statuses(audit, lock),
        samples_run=conformance.samples_run,
        coverage=_coverage_table(targets, audit, conformance),
    )


def law_state(law: LawInfo) -> LawState:
    if law.refutations:
        return LawState.REFUTED
    if not law.proofs:
        return LawState.OPEN
    if any(set(proof.axioms) <= ALLOWED_AXIOMS for proof in law.proofs):
        return LawState.PROVED
    return LawState.UNSOUND


def _lean_error(error: LeanError) -> Finding:
    return Finding(
        FindingKind.LEAN_ERROR,
        error.stage,
        f"The Lean {error.stage} step failed. Correct the Lean error in the log.",
        {"log": error.log[-LOG_TAIL_CHARS:]},
    )


def _law_statuses(audit: Audit, lock: Lock) -> tuple[LawStatus, ...]:
    return tuple(
        LawStatus(
            name=law.name,
            state=law_state(law),
            approved=law.name in lock.laws and lock.laws[law.name].statement == law.statement,
            covers=law.covers,
        )
        for law in audit.laws
    )


def _law_findings(audit: Audit, lock: Lock) -> Iterable[Finding]:
    current = {law.name for law in audit.laws}
    for law in audit.laws:
        yield from _approval_findings(law, lock)
        yield from _proof_findings(law)
    for name in sorted(set(lock.laws) - current):
        yield Finding(FindingKind.REMOVED_LAW, name, f"The lock has this law, but the project does not. Run `leanunit approve {name}` to remove it from the lock.")
    if lock.laws and lock.lean_toolchain not in (None, audit.toolchain):
        yield Finding(
            FindingKind.TOOLCHAIN_CHANGED,
            audit.toolchain,
            f"The lock records Lean {lock.lean_toolchain}, but the project uses Lean {audit.toolchain}. Run `leanunit approve --all` after you examine the laws.",
        )


def _approval_findings(law: LawInfo, lock: Lock) -> Iterable[Finding]:
    if law.problem:
        yield Finding(FindingKind.LAW_PROBLEM, law.name, law.problem)
    approval = lock.laws.get(law.name)
    if approval is None:
        yield Finding(FindingKind.UNAPPROVED_LAW, law.name, f"No human approved this law. Read it, then run `leanunit approve {law.name}`.")
    elif approval.statement != law.statement:
        yield Finding(
            FindingKind.CHANGED_LAW,
            law.name,
            f"The meaning of this law changed after {approval.approved_by} approved it. Read the change, then run `leanunit approve {law.name}`.",
            {"approved": approval.statement, "current": law.statement},
        )


def _proof_findings(law: LawInfo) -> Iterable[Finding]:
    state = law_state(law)
    if state is LawState.REFUTED:
        yield Finding(
            FindingKind.REFUTED_LAW,
            law.name,
            f"Lean has a proof that this law is false: {', '.join(proof.name for proof in law.refutations)}. The code or the law is wrong.",
        )
    elif state is LawState.OPEN:
        yield Finding(FindingKind.OPEN_LAW, law.name, "This law has no proof.")
    elif state is LawState.UNSOUND:
        axioms = sorted({axiom for proof in law.proofs for axiom in proof.axioms} - ALLOWED_AXIOMS)
        yield Finding(
            FindingKind.BAD_AXIOM,
            law.name,
            f"Each proof of this law uses a forbidden axiom: {', '.join(axioms)}.",
            {"axioms": axioms},
        )


def _forbidden_findings(audit: Audit) -> Iterable[Finding]:
    for item in audit.forbidden:
        yield Finding(
            FindingKind.FORBIDDEN_CONSTANT,
            item.name,
            f"A law or a mirror depends on this constant, and it uses {', '.join(item.reasons)}.",
            {"reasons": list(item.reasons)},
        )


@dataclass(frozen=True)
class CoverTargets:
    required: tuple[str, ...]
    excluded: tuple[str, ...]
    errors: tuple[Finding, ...]


def _cover_targets(config: Config) -> CoverTargets:
    required: list[str] = []
    excluded: list[str] = []
    errors: list[Finding] = []
    for target in config.cover:
        try:
            methods = methods_of(config.source_root, target)
        except TargetError as error:
            errors.append(Finding(FindingKind.TARGET_ERROR, target, str(error)))
            continue
        required += [method for method in methods if method not in config.exclude]
        excluded += [method for method in methods if method in config.exclude]
    return CoverTargets(tuple(required), tuple(excluded), tuple(errors))


def _coverage_findings(targets: CoverTargets, audit: Audit) -> Iterable[Finding]:
    mirrored = {mirror.target for mirror in audit.mirrors}
    used = {target for law in audit.laws for target in law.covers}
    yield from targets.errors
    for target in targets.required:
        if target not in mirrored:
            yield Finding(
                FindingKind.UNCOVERED_CODE,
                target,
                "This code is in the cover list, but no model function mirrors it. Run `leanunit new`, or add it to exclude in leanunit.toml.",
            )
    for mirror in audit.mirrors:
        if mirror.target not in used:
            yield Finding(FindingKind.UNUSED_MIRROR, mirror.name, f"No law uses this mirror of {mirror.target}.")


def _coverage_table(targets: CoverTargets, audit: Audit, conformance: ConformanceResult) -> tuple[TargetCoverage, ...]:
    mirrors = {mirror.target: mirror.name for mirror in audit.mirrors}
    laws: dict[str, list[str]] = {}
    for law in audit.laws:
        for target in law.covers:
            laws.setdefault(target, []).append(law.name)
    listed = [*targets.required, *(target for target in mirrors if target not in targets.required)]
    rows = [
        TargetCoverage(
            target=target,
            status=_target_status(target in mirrors, bool(laws.get(target))),
            mirror=mirrors.get(target),
            laws=tuple(laws.get(target, ())),
            lines=conformance.line_totals.get(target),
            missing=conformance.missing_lines.get(target, ()),
        )
        for target in listed
    ]
    return tuple(rows) + tuple(TargetCoverage(target, TargetStatus.EXCLUDED) for target in targets.excluded)


def _target_status(mirrored: bool, has_laws: bool) -> TargetStatus:
    if not mirrored:
        return TargetStatus.NO_MIRROR
    return TargetStatus.COVERED if has_laws else TargetStatus.NO_LAW


def _conformance_findings(config: Config, result: ConformanceResult) -> Iterable[Finding]:
    for message in result.harness_errors:
        yield Finding(FindingKind.HARNESS_ERROR, "runner", message)
    for mismatch in result.mismatches:
        count = result.mismatch_counts.get(mismatch.target, 1)
        yield Finding(
            FindingKind.MISMATCH,
            mismatch.target,
            f"The model and the code disagree on {count} samples. The details show the smallest one.",
            {"args": mismatch.args, "expected": mismatch.expected, "actual": mismatch.actual, "count": count},
        )
    for target, lines in result.missing_lines.items():
        yield Finding(
            FindingKind.MISSING_LINES,
            target,
            f"The samples did not execute {len(lines)} lines of this code.",
            {"lines": {str(number): text for number, text in _source_lines(config, target, lines)}},
        )


def _source_lines(config: Config, target: str, numbers: tuple[int, ...]) -> list[tuple[int, str]]:
    try:
        source = module_file(config.source_root, split_target(target)[0]).read_text().splitlines()
    except TargetError:
        return [(number, "") for number in numbers]
    return [(number, source[number - 1].strip() if number <= len(source) else "") for number in numbers]
