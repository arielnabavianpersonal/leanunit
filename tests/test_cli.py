import pytest

import leanunit.cli as cli
from leanunit.report import Finding, FindingKind, Report, TargetCoverage, TargetStatus
from leanunit.stubs import StubResult


@pytest.fixture
def project(tmp_path):
    assert cli.main(["--root", str(tmp_path), "init", "--cover", "pkg.mod:Thing"]) == cli.EXIT_OK
    return tmp_path


@pytest.mark.parametrize("report, exit_code", [
    (Report(), cli.EXIT_OK),
    (Report(findings=(Finding(FindingKind.OPEN_LAW, "Laws.x", "no proof"),)), cli.EXIT_FAILED),
])
def test_should_exit_with_the_check_result(project, monkeypatch, capsys, report, exit_code):
    monkeypatch.setattr(cli, "run_check", lambda config: report)

    assert cli.main(["--root", str(project), "check", "--json"]) == exit_code
    assert '"passed"' in capsys.readouterr().out


def test_should_exit_with_a_usage_error_when_an_agent_approves(project, monkeypatch, capsys):
    monkeypatch.setenv("LEANUNIT_AGENT", "1")

    assert cli.main(["--root", str(project), "approve", "--all"]) == cli.EXIT_USAGE
    assert "for humans" in capsys.readouterr().err


def test_should_exit_with_a_usage_error_when_the_config_is_missing(tmp_path, capsys):
    assert cli.main(["--root", str(tmp_path), "check"]) == cli.EXIT_USAGE
    assert "leanunit init" in capsys.readouterr().err


def test_should_exit_with_three_when_only_a_human_can_act(project, monkeypatch):
    report = Report(findings=(Finding(FindingKind.UNAPPROVED_LAW, "Laws.x", "approve it"),))
    monkeypatch.setattr(cli, "run_check", lambda config: report)

    assert cli.main(["--root", str(project), "check"]) == cli.EXIT_NEEDS_HUMAN


def test_should_print_the_guide(project, capsys):
    assert cli.main(["--root", str(project), "guide"]) == cli.EXIT_OK
    assert capsys.readouterr().out.startswith("# LeanUnit guide")


def test_should_print_the_coverage_table(project, monkeypatch, capsys):
    row = TargetCoverage("pkg.mod:f", TargetStatus.COVERED, "Model.f", ("Laws.a",), 4, (7,))
    monkeypatch.setattr(cli, "run_check", lambda config: Report(coverage=(row,)))

    assert cli.main(["--root", str(project), "coverage"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "covered    1 law    3/4 lines     pkg.mod:f" in out
    assert "missing lines: 7" in out
    assert "Coverage: 1 of 1 targets have laws. Samples executed 3 of 4 lines (75%)." in out


def test_should_fail_coverage_when_the_lean_step_fails(project, monkeypatch):
    report = Report(findings=(Finding(FindingKind.LEAN_ERROR, "build", "boom"),))
    monkeypatch.setattr(cli, "run_check", lambda config: report)

    assert cli.main(["--root", str(project), "coverage"]) == cli.EXIT_FAILED


def test_should_say_the_next_steps_after_new(project, monkeypatch, capsys):
    result = StubResult(name="Thing", created=(), mirrors=("pkg.mod:Thing.run",), in_cover_list=False)
    monkeypatch.setattr(cli, "scaffold_target", lambda config, target, name: result)

    assert cli.main(["--root", str(project), "new", "pkg.mod:Other"]) == cli.EXIT_OK
    assert 'add "pkg.mod:Other" to the cover list' in capsys.readouterr().out
