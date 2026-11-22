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
class Report:
    findings: tuple[Finding, ...] = ()
    laws: tuple[LawStatus, ...] = ()
    samples_run: int = 0

    @property
    def passed(self) -> bool:
        return not self.findings

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
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def render(self) -> str:
        verdict = "PASSED" if self.passed else f"FAILED ({len(self.findings)} findings)"
        lines = [f"NoUnit check: {verdict}", "", f"Laws ({len(self.laws)}):"]
        lines += [
            f"  {law.state.value:<8} {'approved' if law.approved else 'NOT approved':<13} {law.name}" for law in self.laws
        ]
        lines += ["", f"Conformance samples: {self.samples_run}"]
        if self.findings:
            lines += ["", "Findings:"]
            for finding in self.findings:
                lines += [f"  [{finding.kind.label}] {finding.subject}", f"      {finding.message}"]
        return "\n".join(lines) + "\n"
