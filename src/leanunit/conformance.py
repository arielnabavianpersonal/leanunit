from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from leanunit.config import Config
from leanunit.lean import Sample

RUNNER_TIMEOUT_SECONDS = 600
MAX_HARNESS_ERRORS = 5


@dataclass(frozen=True)
class Mismatch:
    target: str
    args: list[Any]
    expected: Any
    actual: Any


@dataclass(frozen=True)
class ConformanceResult:
    samples_run: int = 0
    mismatches: tuple[Mismatch, ...] = ()
    mismatch_counts: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    missing_lines: Mapping[str, tuple[int, ...]] = field(default_factory=lambda: MappingProxyType({}))
    line_totals: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    harness_errors: tuple[str, ...] = ()


def same(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def run_conformance(config: Config, samples: Sequence[Sample]) -> ConformanceResult:
    if not samples:
        return ConformanceResult()
    requests = "".join(json.dumps({"target": sample.target, "args": sample.args}) + "\n" for sample in samples)
    command = config.language.runner_command(config.runtime, config.source_root)
    try:
        completed = subprocess.run(
            command, input=requests, capture_output=True, text=True, cwd=config.root, timeout=RUNNER_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return ConformanceResult(harness_errors=(f"the {config.language.name} runner did not run: {error}",))
    lines = completed.stdout.splitlines()
    if completed.returncode != 0 or len(lines) != len(samples) + 1:
        return ConformanceResult(harness_errors=(f"the {config.language.name} runner failed: {completed.stderr[-2000:]}",))
    return _compare(samples, [json.loads(line) for line in lines[:-1]], json.loads(lines[-1])["coverage"])


def _compare(samples: Sequence[Sample], outcomes: list[dict[str, Any]], coverage: dict[str, Any]) -> ConformanceResult:
    smallest: dict[str, Mismatch] = {}
    counts: dict[str, int] = {}
    errors: list[str] = []
    for sample, outcome in zip(samples, outcomes):
        if "error" in outcome:
            if outcome["error"] not in errors:
                errors.append(outcome["error"])
            continue
        if same(sample.expected, outcome):
            continue
        counts[sample.target] = counts.get(sample.target, 0) + 1
        mismatch = Mismatch(sample.target, sample.args, sample.expected, outcome)
        current = smallest.get(sample.target)
        if current is None or _size(mismatch.args) < _size(current.args):
            smallest[sample.target] = mismatch
    return ConformanceResult(
        samples_run=len(samples),
        mismatches=tuple(smallest[target] for target in sorted(smallest)),
        mismatch_counts=MappingProxyType(counts),
        missing_lines=MappingProxyType({
            target: tuple(entry["missing"]) for target, entry in sorted(coverage.items()) if entry["missing"]
        }),
        line_totals=MappingProxyType({target: entry["lines"] for target, entry in sorted(coverage.items())}),
        harness_errors=tuple(errors[:MAX_HARNESS_ERRORS]),
    )


def _size(args: list[Any]) -> int:
    return len(json.dumps(args))
