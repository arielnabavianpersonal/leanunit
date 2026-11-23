from pathlib import Path

import pytest

from leanunit.lean import Audit, LawInfo, LeanProject

pytestmark = pytest.mark.lean

FIXTURE = Path(__file__).parent / "fixtures" / "lean-mini"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


@pytest.fixture(scope="module")
def audit() -> Audit:
    return LeanProject(FIXTURE).audit()


def law(audit: Audit, short_name: str) -> LawInfo:
    return next(item for item in audit.laws if item.name == f"Laws.Mini.{short_name}")


def test_should_find_a_proof_with_allowed_axioms_when_the_law_is_proved(audit):
    proved = law(audit, "inc_positive")

    assert [proof.name for proof in proved.proofs] == ["Proofs.Mini.inc_positive_holds"]
    assert set(proved.proofs[0].axioms) <= ALLOWED_AXIOMS
    assert proved.refutations == ()
    assert proved.problem is None


def test_should_find_a_refutation_when_the_law_is_false(audit):
    refuted = law(audit, "inc_big")

    assert refuted.proofs == ()
    assert [proof.name for proof in refuted.refutations] == ["Proofs.Mini.inc_big_refuted"]


def test_should_show_sorry_when_the_proof_has_a_gap(audit):
    assert law(audit, "inc_nonzero").proofs[0].axioms == ("sorryAx",)


def test_should_show_a_new_axiom_when_the_proof_uses_one(audit):
    assert "Proofs.Mini.magic" in law(audit, "inc_at_least_one").proofs[0].axioms


def test_should_flag_implemented_by_when_a_law_depends_on_it(audit):
    flagged = {item.name: item.reasons for item in audit.forbidden}

    assert flagged["Model.Mini.double"] == ("implemented_by",)


def test_should_have_no_proof_when_nobody_proved_the_law(audit):
    open_law = law(audit, "unproved")

    assert open_law.proofs == () and open_law.refutations == ()


def test_should_list_the_mirror_with_its_target_and_arity(audit):
    assert [(m.name, m.target, m.arity) for m in audit.mirrors] == [("Model.Mini.inc", "mini:inc", 1)]


def test_should_list_covered_targets_when_a_law_uses_a_mirror(audit):
    assert law(audit, "inc_positive").covers == ("mini:inc",)
    assert law(audit, "unproved").covers == ()


def hash_after_edit(copy_lean_project, file: str, old: str, new: str) -> tuple[str, str]:
    project = copy_lean_project("lean-mini")
    before = law(LeanProject(project).audit(), "inc_positive").statement
    path = project / file
    path.write_text(path.read_text().replace(old, new, 1))
    after = law(LeanProject(project).audit(), "inc_positive").statement
    return before, after


def test_should_change_the_hash_when_a_helper_of_the_law_changes(copy_lean_project):
    before, after = hash_after_edit(copy_lean_project, "Model/Mini.lean", "n > 0", "n ≥ 1")

    assert before != after


def test_should_keep_the_hash_when_a_mirrored_function_changes(copy_lean_project):
    before, after = hash_after_edit(copy_lean_project, "Model/Mini.lean", ".ok () (n + 1)", ".ok () (1 + n)")

    assert before == after


def test_should_keep_the_hash_when_blank_lines_move_the_law(copy_lean_project):
    before, after = hash_after_edit(copy_lean_project, "Laws/Mini.lean", "namespace Laws.Mini\n", "namespace Laws.Mini\n\n\n\n")

    assert before == after
