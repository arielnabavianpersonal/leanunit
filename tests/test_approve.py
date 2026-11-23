import pytest

from leanunit.approve import ApproveError, run_approve
from leanunit.lock import LawApproval, Lock, load_lock, save_lock
from tests.fakes import FakeLean, audit, law, make_config

TODAY = "2026-11-22"
APPROVER = "dev@example.com"


@pytest.fixture
def config(tmp_path):
    return make_config(tmp_path)


def approve(config, names=(), approve_all=False, current=None, environ=None):
    lean = FakeLean(current or audit(law(), law(name="Laws.Main.second", statement="sha256:c")))
    return run_approve(config, list(names), approve_all, APPROVER, TODAY, lean=lean, environ=environ or {})


def test_should_write_every_law_and_the_toolchain_when_approving_all(config):
    result = approve(config, approve_all=True)

    lock = load_lock(config.lock_path)
    assert result.approved == ("Laws.Main.double_positive", "Laws.Main.second")
    assert lock.laws["Laws.Main.second"] == LawApproval("sha256:c", ("sample_mod:double",), APPROVER, TODAY)
    assert lock.lean_toolchain == "4.36.0"


def test_should_accept_a_short_name_when_it_is_unique(config):
    result = approve(config, names=["second"])

    assert result.approved == ("Laws.Main.second",)
    assert list(load_lock(config.lock_path).laws) == ["Laws.Main.second"]


def test_should_remove_a_law_from_the_lock_when_it_is_gone(config):
    save_lock(config.lock_path, Lock().approve("Laws.Main.old", LawApproval("sha256:z", (), APPROVER, TODAY)))

    result = approve(config, approve_all=True)

    assert result.removed == ("Laws.Main.old",)
    assert "Laws.Main.old" not in load_lock(config.lock_path).laws


def test_should_refuse_when_an_agent_starts_it(config):
    with pytest.raises(ApproveError, match="for humans"):
        approve(config, approve_all=True, environ={"LEANUNIT_AGENT": "1"})
    assert not config.lock_path.exists()


@pytest.mark.parametrize("names, message", [
    ([], "Name the laws"),
    (["unknown"], "No law is named"),
])
def test_should_refuse_when_the_names_are_wrong(config, names, message):
    with pytest.raises(ApproveError, match=message):
        approve(config, names=names)


def test_should_refuse_a_short_name_that_matches_two_laws(config):
    current = audit(law(name="Laws.A.same"), law(name="Laws.B.same"))

    with pytest.raises(ApproveError, match="more than one"):
        approve(config, names=["same"], current=current)


def test_should_refuse_a_law_that_has_a_problem(config):
    with pytest.raises(ApproveError, match="problems"):
        approve(config, approve_all=True, current=audit(law(problem="not a Prop")))
