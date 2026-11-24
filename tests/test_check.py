import pytest

from leanunit.check import run_check
from leanunit.lean import ForbiddenInfo, LeanError, MirrorInfo, ProofInfo, Sample
from leanunit.lock import ExclusionApproval, LawApproval, Lock, save_lock
from leanunit.report import LawState, LawStatus, Owner, TargetStatus
from tests.fakes import MIRROR, SAMPLES, FakeLean, audit, law, make_config
from tests.sample_code import write_sample_module


@pytest.fixture
def config(tmp_path):
    write_sample_module(tmp_path)
    return make_config(tmp_path)


def approve(config, *laws, toolchain="4.36.0"):
    approvals = {item.name: LawApproval(item.statement, item.covers, "dev@example.com", "2026-11-22") for item in laws}
    save_lock(config.lock_path, Lock(lean_toolchain=toolchain, laws=approvals))


def kinds(report):
    return sorted(finding.kind.label for finding in report.findings)


def test_should_pass_when_every_condition_holds(config):
    approve(config, law())

    report = run_check(config, FakeLean(audit(law())))

    assert report.passed, report.render()
    assert report.laws == (LawStatus(law().name, LawState.PROVED, True, ("sample_mod:double",)),)
    assert report.samples_run == len(SAMPLES)


@pytest.mark.parametrize("current, expected", [
    (law(statement="sha256:b"), ["changed_law"]),
    (law(proofs=()), ["open_law"]),
    (law(proofs=(ProofInfo("Proofs.gap", ("sorryAx",)),)), ["bad_axiom"]),
    (law(refutations=(ProofInfo("Proofs.counterexample", ("propext",)),)), ["refuted_law"]),
    (law(problem="a law must be a definition of type Prop"), ["law_problem"]),
])
def test_should_report_the_law_finding_when_a_law_is_not_sound(config, current, expected):
    approve(config, law())

    assert kinds(run_check(config, FakeLean(audit(current)))) == expected


def test_should_accept_a_law_when_one_of_its_proofs_is_clean(config):
    approve(config, law())
    current = law(proofs=(ProofInfo("Proofs.gap", ("sorryAx",)), ProofInfo("Proofs.clean", ())))

    assert run_check(config, FakeLean(audit(current))).passed


def test_should_report_new_and_removed_laws_when_the_lock_is_out_of_date(config):
    approve(config, law(name="Laws.Main.old"))

    report = run_check(config, FakeLean(audit(law())))

    assert kinds(report) == ["removed_law", "unapproved_law"]
    assert {finding.kind.owner for finding in report.findings} == {Owner.HUMAN}


def test_should_report_the_toolchain_when_it_differs_from_the_lock(config):
    approve(config, law(), toolchain="4.35.0")

    assert kinds(run_check(config, FakeLean(audit(law())))) == ["toolchain_changed"]


def test_should_report_forbidden_constants(config):
    approve(config, law())
    current = audit(law(), forbidden=(ForbiddenInfo("Model.fast", ("implemented_by",)),))

    assert kinds(run_check(config, FakeLean(current))) == ["forbidden_constant"]


def test_should_report_uncovered_code_and_unused_mirrors(config):
    config = make_config(config.root, cover=("sample_mod:Box",), exclude=("sample_mod:Box.make", "sample_mod:Box.noisy"))
    approve(config, law(covers=()))

    report = run_check(config, FakeLean(audit(law(covers=())), samples=()))

    uncovered = sorted(finding.subject for finding in report.findings if finding.kind.label == "uncovered_code")
    assert uncovered == ["sample_mod:Box.add", "sample_mod:Box.add_all", "sample_mod:Box.first_name"]
    assert [finding.subject for finding in report.findings if finding.kind.label == "unused_mirror"] == [MIRROR.name]


def test_should_report_a_target_error_when_a_cover_target_is_missing(config):
    config = make_config(config.root, cover=("sample_mod:Nothing",))
    approve(config, law())

    assert "target_error" in kinds(run_check(config, FakeLean(audit(law()))))


def test_should_report_the_smallest_mismatch_when_the_model_and_code_disagree(config):
    approve(config, law())
    wrong = (*SAMPLES, Sample("sample_mod:double", [9], {"self": None, "return": 1}))

    report = run_check(config, FakeLean(audit(law()), samples=wrong))

    assert kinds(report) == ["mismatch"]
    assert dict(report.findings[0].details)["actual"] == {"self": None, "return": 18}


def test_should_show_the_source_of_missing_lines(config):
    approve(config, law())

    report = run_check(config, FakeLean(audit(law()), samples=SAMPLES[:1]))

    assert kinds(report) == ["missing_lines"]
    assert list(dict(report.findings[0].details)["lines"].values()) == ["return 0"]


def test_should_stop_when_the_audit_fails(config):
    report = run_check(config, FakeLean(audit_error=LeanError("build", "error: boom")))

    assert kinds(report) == ["lean_error"]
    assert "boom" in dict(report.findings[0].details)["log"]


def test_should_keep_the_law_findings_when_the_sampler_fails(config):
    approve(config, law())

    report = run_check(config, FakeLean(audit(law(proofs=())), sample_error=LeanError("sampler", "no Sample")))

    assert kinds(report) == ["lean_error", "open_law"]


def test_should_list_coverage_rows_for_each_target(config):
    config = make_config(config.root, cover=("sample_mod:double", "sample_mod:Box"), exclude=("sample_mod:Box.make",))
    approve(config, law())

    report = run_check(config, FakeLean(audit(law()), samples=SAMPLES[:1]))

    rows = {row.target: row for row in report.coverage}
    assert rows["sample_mod:double"].status is TargetStatus.COVERED
    assert (rows["sample_mod:double"].lines, rows["sample_mod:double"].executed) == (3, 2)
    assert rows["sample_mod:Box.add"].status is TargetStatus.NO_MIRROR
    assert rows["sample_mod:Box.make"].status is TargetStatus.EXCLUDED


def test_should_mark_a_mirror_without_laws(config):
    approve(config, law(covers=()))

    report = run_check(config, FakeLean(audit(law(covers=()))))

    assert [row.status for row in report.coverage] == [TargetStatus.NO_LAW]


def test_should_ask_a_human_to_approve_an_exclusion_when_the_lock_lacks_it(config):
    config = make_config(config.root, exclude=("sample_mod:Box.make",))
    approve(config, law())

    report = run_check(config, FakeLean(audit(law())))

    assert kinds(report) == ["unapproved_exclusion"]
    assert report.needs_human_only


def test_should_accept_an_exclusion_when_a_human_approved_it(config):
    config = make_config(config.root, exclude=("sample_mod:Box.make",))
    approvals = {law().name: LawApproval(law().statement, law().covers, "dev@example.com", "2026-11-22")}
    exclusions = {"sample_mod:Box.make": ExclusionApproval("dev@example.com", "2026-11-24")}
    save_lock(config.lock_path, Lock(lean_toolchain="4.36.0", laws=approvals, exclusions=exclusions))

    assert run_check(config, FakeLean(audit(law()))).passed


METER = {"value": 3}
METER_TARGETS = ("sample_mod:Meter.doubled", "sample_mod:Meter.__str__", "sample_mod:Meter.zero")
METER_MIRRORS = tuple(
    MirrorInfo(name=f"Model.m{index}", module="Model.Main", target=target, arity=1) for index, target in enumerate(METER_TARGETS)
)
METER_SAMPLES = (
    Sample("sample_mod:Meter.doubled", [METER], {"self": METER, "return": 6}),
    Sample("sample_mod:Meter.__str__", [METER], {"self": METER, "return": "3 m"}),
    Sample("sample_mod:Meter.zero", [], {"self": None, "return": {"value": 0}}),
)


def test_should_require_the_samples_to_run_each_line_of_a_private_helper(config):
    config = make_config(config.root, cover=("sample_mod:Meter",))
    meter_law = law(covers=METER_TARGETS)
    approve(config, meter_law)

    report = run_check(config, FakeLean(audit(meter_law, mirrors=METER_MIRRORS), samples=METER_SAMPLES))

    assert [(finding.kind.label, finding.subject) for finding in report.findings] == [("missing_lines", "sample_mod:Meter._scale")]
    assert {row.target: row.status for row in report.coverage}["sample_mod:Meter._scale"] is TargetStatus.HELPER
