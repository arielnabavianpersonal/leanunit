import pytest

from leanunit.check import run_check
from leanunit.config import load_config
from leanunit.scaffold import init_project
from leanunit.stubs import StubError, describe_target, lean_name, render_files, scaffold_target
from tests.fakes import make_config
from tests.sample_code import write_sample_module

DESCRIPTION = {
    "target": "pkg.mod:Holder",
    "owner": {"kind": "dataclass", "name": "Holder"},
    "functions": [
        {
            "target": "pkg.mod:Holder.put",
            "name": "put",
            "params": [{"name": "from", "type": {"kind": "str"}}],
            "returns": {"kind": "optional", "item": {"kind": "int"}},
        }
    ],
    "types": {
        "Holder": {"fields": [{"name": "parts", "type": {"kind": "list", "item": {"kind": "dataclass", "name": "Part"}}}]},
        "Part": {"fields": [{"name": "end", "type": {"kind": "dict", "value": {"kind": "any"}}}]},
    },
}


def test_should_write_dependencies_first_and_escape_lean_keywords():
    model = {str(path): text for path, text in render_files("Holder", DESCRIPTION).items()}["Model/Holder.lean"]

    assert model.index("structure Part where") < model.index("structure Holder where")
    assert "  «end» : (Dict Val)" in model
    assert "  parts : (List Part)" in model
    assert '@[mirror "pkg.mod:Holder.put"]' in model
    assert "def put (self : Holder) («from» : String) : Outcome Holder (Option Int) :=" in model
    assert '.raise "NotImplementedError" self' in model


def test_should_write_a_sample_instance_for_each_type_in_order():
    files = {str(path): text for path, text in render_files("Holder", DESCRIPTION).items()}

    gen = files["Gen/Holder.lean"]
    assert gen.index("instance : Sample Part") < gen.index("instance : Sample Holder")
    assert "«end» := ← Sample.sample" in gen
    assert "import Model.Holder" in files["Laws/Holder.lean"]
    assert "import Laws.Holder" in files["Proofs/Holder.lean"]


def test_should_use_unit_state_for_a_function():
    description = {
        "target": "pkg.mod:double",
        "owner": None,
        "functions": [{"target": "pkg.mod:double", "name": "double", "params": [{"name": "n", "type": {"kind": "int"}}], "returns": {"kind": "int"}}],
        "types": {},
    }

    model = next(text for path, text in render_files("Mod", description).items() if path.parts[0] == "Model")

    assert "def double (n : Int) : Outcome Unit Int :=" in model
    assert '.raise "NotImplementedError" ()' in model


def test_should_refuse_a_function_with_too_many_arguments():
    params = [{"name": f"p{index}", "type": {"kind": "int"}} for index in range(8)]
    description = {**DESCRIPTION, "functions": [{**DESCRIPTION["functions"][0], "params": params}]}

    with pytest.raises(StubError, match="supports 1 to 8"):
        render_files("Holder", description)


@pytest.fixture
def config(tmp_path):
    write_sample_module(tmp_path)
    return make_config(tmp_path, cover=("sample_mod:Box",), exclude=("sample_mod:Box.noisy",))


def test_should_describe_the_types_and_written_methods_of_a_dataclass(config):
    description = describe_target(config, "sample_mod:Box")

    assert [function["name"] for function in description["functions"]] == ["add", "add_all", "first_name", "noisy"]
    assert description["types"]["Box"]["fields"][0] == {
        "name": "items", "type": {"kind": "dict", "value": {"kind": "dataclass", "name": "Item"}}
    }
    assert description["functions"][0]["params"][1] == {"name": "value", "type": {"kind": "any"}}


@pytest.mark.parametrize("target, message", [
    ("sample_mod:missing", "not a class or a Python function"),
    ("no_such_module:thing", "cannot find"),
])
def test_should_raise_when_the_target_cannot_be_described(config, target, message):
    with pytest.raises(StubError, match=message):
        describe_target(config, target)


def test_should_write_four_files_without_excluded_functions(config):
    result = scaffold_target(config, "sample_mod:Box")

    assert sorted(path.relative_to(config.lean_project).as_posix() for path in result.created) == [
        "Gen/Box.lean", "Laws/Box.lean", "Model/Box.lean", "Proofs/Box.lean"
    ]
    assert result.mirrors == ("sample_mod:Box.add", "sample_mod:Box.add_all", "sample_mod:Box.first_name")
    assert result.in_cover_list


def test_should_not_overwrite_existing_files(config):
    scaffold_target(config, "sample_mod:Box")

    with pytest.raises(StubError, match="does not overwrite"):
        scaffold_target(config, "sample_mod:Box")


@pytest.mark.lean
def test_should_build_and_run_the_stubs_without_harness_errors(tmp_path):
    write_sample_module(tmp_path)
    init_project(tmp_path, ".", ("sample_mod:Box",))
    config = load_config(tmp_path)

    scaffold_target(config, "sample_mod:Box")
    report = run_check(config)

    kinds = {finding.kind.label for finding in report.findings}
    assert kinds == {"mismatch", "unused_mirror", "uncovered_code"}
    assert {finding.subject for finding in report.findings if finding.kind.label == "uncovered_code"} == {"sample_mod:Box.make"}


def test_should_describe_keyword_only_parameters(config):
    description = describe_target(config, "sample_mod:window")

    assert [param["name"] for param in description["functions"][0]["params"]] == ["text", "start", "end", "fill", "label"]


@pytest.mark.lean
def test_should_build_and_run_a_five_argument_mirror_without_harness_errors(tmp_path):
    write_sample_module(tmp_path)
    init_project(tmp_path, ".", ("sample_mod:window",))
    config = load_config(tmp_path)

    scaffold_target(config, "sample_mod:window", "Window")
    report = run_check(config)

    assert {finding.kind.label for finding in report.findings} == {"mismatch", "unused_mirror"}


@pytest.mark.parametrize("name", ["prefix", "notation", "mutual", "local"])
def test_should_escape_lean_command_keywords(name):
    assert lean_name(name) == f"«{name}»"
