from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class Owner(Enum):
    HUMAN = "human"
    AGENT = "agent"


class FindingKind(Enum):
    LEAN_ERROR = ("lean_error", Owner.AGENT)
    LAW_PROBLEM = ("law_problem", Owner.AGENT)
    UNAPPROVED_LAW = ("unapproved_law", Owner.HUMAN)
    CHANGED_LAW = ("changed_law", Owner.HUMAN)
    REMOVED_LAW = ("removed_law", Owner.HUMAN)
    TOOLCHAIN_CHANGED = ("toolchain_changed", Owner.HUMAN)
    OPEN_LAW = ("open_law", Owner.AGENT)
    REFUTED_LAW = ("refuted_law", Owner.AGENT)
    BAD_AXIOM = ("bad_axiom", Owner.AGENT)
    FORBIDDEN_CONSTANT = ("forbidden_constant", Owner.AGENT)
    MISMATCH = ("mismatch", Owner.AGENT)
    MISSING_LINES = ("missing_lines", Owner.AGENT)
    HARNESS_ERROR = ("harness_error", Owner.AGENT)
    UNCOVERED_CODE = ("uncovered_code", Owner.AGENT)
    UNUSED_MIRROR = ("unused_mirror", Owner.AGENT)
    TARGET_ERROR = ("target_error", Owner.HUMAN)

    def __init__(self, label: str, owner: Owner) -> None:
        self.label = label
        self.owner = owner


class LawState(Enum):
    PROVED = "proved"
    REFUTED = "refuted"
    OPEN = "open"
    UNSOUND = "unsound"


class TargetStatus(Enum):
    COVERED = "covered"
    NO_LAW = "no law"
    NO_MIRROR = "no mirror"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class Finding:
    kind: FindingKind
    subject: str
    message: str
    details: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.label,
            "owner": self.kind.owner.value,
            "subject": self.subject,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class LawStatus:
    name: str
    state: LawState
    approved: bool
    covers: tuple[str, ...]


@dataclass(frozen=True)
class TargetCoverage:
    target: str
    status: TargetStatus
    mirror: str | None = None
    laws: tuple[str, ...] = ()
    lines: int | None = None
    missing: tuple[int, ...] = ()

    @property
    def executed(self) -> int | None:
        return None if self.lines is None else self.lines - len(self.missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "status": self.status.value,
            "mirror": self.mirror,
            "laws": list(self.laws),
            "lines": self.lines,
            "executed": self.executed,
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...] = ()
    laws: tuple[LawStatus, ...] = ()
    samples_run: int = 0
    coverage: tuple[TargetCoverage, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def needs_human_only(self) -> bool:
        return bool(self.findings) and not self.owned_by(Owner.AGENT)

    def owned_by(self, owner: Owner) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.kind.owner is owner)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "samplesRun": self.samples_run,
            "laws": [
                {"name": law.name, "state": law.state.value, "approved": law.approved, "covers": list(law.covers)}
                for law in self.laws
            ],
            "findings": [finding.to_dict() for finding in self.findings],
            "coverage": [entry.to_dict() for entry in self.coverage],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def render(self) -> str:
        verdict = "PASSED" if self.passed else f"FAILED ({len(self.findings)} findings)"
        lines = [f"LeanUnit check: {verdict}", "", f"Laws ({len(self.laws)}):"]
        lines += [
            f"  {law.state.value:<8} {'approved' if law.approved else 'NOT approved':<13} {law.name}" for law in self.laws
        ]
        lines += ["", f"Conformance samples: {self.samples_run}"]
        if self.coverage:
            lines.append(self._coverage_summary())
        if self.findings:
            lines += ["", "Findings:"]
            for finding in self.findings:
                lines += [f"  [{finding.kind.label}] {finding.subject}", f"      {finding.message}"]
        return "\n".join(lines) + "\n"

    def render_coverage(self) -> str:
        lines = ["LeanUnit coverage", ""]
        for entry in self.coverage:
            laws = f"{len(entry.laws)} law{'s' if len(entry.laws) != 1 else ''}" if entry.mirror else "-"
            executed = f"{entry.executed}/{entry.lines} lines" if entry.lines else "-"
            lines.append(f"  {entry.status.value:<10} {laws:<8} {executed:<13} {entry.target}")
            if entry.missing:
                lines.append(f"      missing lines: {', '.join(map(str, entry.missing))}")
        lines += ["", self._coverage_summary()]
        return "\n".join(lines) + "\n"

    def _coverage_summary(self) -> str:
        counted = [entry for entry in self.coverage if entry.status is not TargetStatus.EXCLUDED]
        covered = sum(entry.status is TargetStatus.COVERED for entry in counted)
        total_lines = sum(entry.lines or 0 for entry in counted)
        executed = sum(entry.executed or 0 for entry in counted)
        share = f" ({executed * 100 // total_lines}%)" if total_lines else ""
        return f"Coverage: {covered} of {len(counted)} targets have laws. Samples executed {executed} of {total_lines} lines{share}."

