import pytest

import nounit.cli as cli
from nounit.report import Finding, FindingKind, Report


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
    monkeypatch.setenv("NOUNIT_AGENT", "1")

    assert cli.main(["--root", str(project), "approve", "--all"]) == cli.EXIT_USAGE
    assert "for humans" in capsys.readouterr().err


def test_should_exit_with_a_usage_error_when_the_config_is_missing(tmp_path, capsys):
    assert cli.main(["--root", str(tmp_path), "check"]) == cli.EXIT_USAGE
    assert "nounit init" in capsys.readouterr().err
