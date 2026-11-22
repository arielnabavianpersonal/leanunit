import shutil
from pathlib import Path

import pytest

from nounit.approve import run_approve
from nounit.check import run_check
from nounit.config import load_config
from tests.conftest import NOUNIT_LEAN

pytestmark = pytest.mark.lean

EXAMPLE = Path(__file__).parents[1] / "examples" / "strands-interrupt"
REFUTED = "Laws.Interrupt.resume_bumps_version_on_change"


@pytest.fixture
def example(tmp_path):
    target = tmp_path / "strands-interrupt"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".lake", "NoUnitGenerated", "lake-manifest.json", ".nounit"))
    lakefile = target / "lean" / "lakefile.toml"
    lakefile.write_text(lakefile.read_text().replace('path = "../../../src/nounit/lean"', f'path = "{NOUNIT_LEAN}"'))
    return load_config(target)


def kinds(report):
    return sorted({finding.kind.label for finding in report.findings})


def test_should_ask_a_human_to_approve_each_law_when_the_lock_is_empty(example):
    report = run_check(example)

    assert kinds(report) == ["refuted_law", "unapproved_law"]
    assert len([finding for finding in report.findings if finding.kind.label == "unapproved_law"]) == len(report.laws)


def test_should_leave_only_the_refuted_law_after_approval(example):
    run_approve(example, [], True, "dev@example.com", "2026-11-22", environ={})

    report = run_check(example)

    assert [(finding.kind.label, finding.subject) for finding in report.findings] == [("refuted_law", REFUTED)]
    assert report.samples_run == example.samples * 8


def test_should_find_a_mismatch_when_the_code_changes_behavior(example):
    run_approve(example, [], True, "dev@example.com", "2026-11-22", environ={})
    code = example.source_root / "strands" / "interrupt.py"
    code.write_text(code.read_text().replace("and interrupt.response is not None", "", 1))

    report = run_check(example)

    assert ("mismatch", "strands.interrupt:_InterruptState.end_tool_cycle") in {
        (finding.kind.label, finding.subject) for finding in report.findings
    }
