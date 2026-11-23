import subprocess
import sys

import pytest

from leanunit.fix import FixError, build_prompt, run_fix
from leanunit.report import Finding, FindingKind, Report
from tests.fakes import make_config

FAILED = Report(findings=(Finding(FindingKind.OPEN_LAW, "Laws.Main.x", "This law has no proof."),))
HUMAN_ONLY = Report(findings=(Finding(FindingKind.UNAPPROVED_LAW, "Laws.Main.x", "Approve it."),))
PASSED = Report()

AGENT_SCRIPT = '''
import os, sys
from pathlib import Path
root = Path.cwd()
(root / "prompt.txt").write_text(sys.stdin.read())
(root / "agent_env.txt").write_text(os.environ.get("LEANUNIT_AGENT", ""))
(root / "lean" / "Proofs" / "P.lean").write_text("theorem proved : True := trivial\\n")
(root / "leanunit.lock").write_text("tampered")
(root / "sample_mod.py").write_text("tampered")
(root / "new_code.py").write_text("print(1)")
(root / ".leanunit").mkdir(exist_ok=True)
(root / ".leanunit" / "diagnosis.md").write_text("open_law: proved it")
'''


class SequenceCheck:
    def __init__(self, *reports):
        self.reports = list(reports)
        self.calls = 0

    def __call__(self, config):
        self.calls += 1
        return self.reports.pop(0)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "leanunit.toml").write_text("[python]\n")
    (tmp_path / "leanunit.lock").write_text("original lock")
    (tmp_path / "sample_mod.py").write_text("original code")
    (tmp_path / "lean" / "Proofs").mkdir(parents=True)
    (tmp_path / "lean" / "Proofs" / "P.lean").write_text("theorem proved : True := sorry\n")
    (tmp_path / "lean" / "helper.py").write_text("lean side")
    script = tmp_path / "agent.py"
    script.write_text(AGENT_SCRIPT)
    return make_config(tmp_path, agent_command=(sys.executable, str(script)))


def test_should_restore_protected_files_and_keep_proofs_when_the_agent_runs(project):
    check = SequenceCheck(FAILED, PASSED)

    result = run_fix(project, check=check)

    root = project.root
    assert (result.started_agent, result.agent_exit_code, check.calls) == (True, 0, 2)
    assert result.restored == ("leanunit.lock", "new_code.py", "sample_mod.py")
    assert (root / "leanunit.lock").read_text() == "original lock"
    assert (root / "sample_mod.py").read_text() == "original code"
    assert not (root / "new_code.py").exists()
    assert (root / "lean" / "Proofs" / "P.lean").read_text() == "theorem proved : True := trivial\n"
    assert result.after.passed
    assert result.diagnosis == "open_law: proved it"


def test_should_send_the_guide_and_the_report_to_the_agent(project):
    run_fix(project, check=SequenceCheck(FAILED, PASSED))

    prompt = (project.root / "prompt.txt").read_text()
    assert "# LeanUnit guide" in prompt
    assert "## You run inside `leanunit fix`" in prompt
    assert '"kind": "open_law"' in prompt
    assert (project.root / "agent_env.txt").read_text() == "1"


@pytest.mark.parametrize("report", [PASSED, HUMAN_ONLY])
def test_should_not_start_the_agent_when_it_has_nothing_to_do(project, report):
    def spawn(*args, **kwargs):
        raise AssertionError("the agent must not start")

    result = run_fix(project, check=SequenceCheck(report), spawn=spawn)

    assert not result.started_agent
    assert result.after is report


def test_should_raise_when_no_agent_command_is_set(project):
    config = make_config(project.root)

    with pytest.raises(FixError, match="agent command"):
        run_fix(config, check=SequenceCheck(FAILED))


def test_should_check_again_when_the_agent_times_out(project):
    def spawn(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    check = SequenceCheck(FAILED, FAILED)

    result = run_fix(project, check=check, spawn=spawn)

    assert (result.agent_exit_code, check.calls) == (None, 2)


def test_should_send_the_intent_and_the_code_diff_to_the_agent(project):
    root = project.root
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "sample_mod.py"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "base"], cwd=root, check=True
    )
    (root / "sample_mod.py").write_text("changed code")

    prompt = build_prompt(project, FAILED, intent="I removed the guard on purpose.")

    assert "I removed the guard on purpose." in prompt
    assert "+changed code" in prompt


def test_should_restore_the_leanunit_library_when_the_agent_edits_it(project, monkeypatch, tmp_path_factory):
    library = tmp_path_factory.mktemp("library")
    (library / "LeanUnit.lean").write_text("trusted")
    monkeypatch.setattr("leanunit.fix.LEANUNIT_LEAN", library)
    script = project.root / "agent.py"
    script.write_text(f"from pathlib import Path\nPath({str(library / 'LeanUnit.lean')!r}).write_text('weakened')\n")

    result = run_fix(project, check=SequenceCheck(FAILED, PASSED))

    assert (library / "LeanUnit.lean").read_text() == "trusted"
    assert str(library / "LeanUnit.lean") in result.restored
