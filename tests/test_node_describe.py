import pytest

from leanunit.config import load_config
from leanunit.check import run_check
from leanunit.languages import TYPESCRIPT
from leanunit.pycode import TargetError
from leanunit.scaffold import init_project
from leanunit.stubs import scaffold_target
from tests.sample_node import write_node_samples

pytestmark = [pytest.mark.node, pytest.mark.typescript]


@pytest.fixture
def source_root(tmp_path):
    return write_node_samples(tmp_path)


def describe(source_root, target):
    return TYPESCRIPT.describe(TYPESCRIPT.default_runtime, source_root, source_root, target)


def test_should_describe_the_fields_and_methods_of_a_class(source_root):
    description = describe(source_root, "typed:Box")

    assert description["owner"] == {"kind": "dataclass", "name": "Box"}
    assert [function["name"] for function in description["functions"]] == ["add", "names"]
    assert description["types"]["Box"]["fields"] == [
        {"name": "items", "type": {"kind": "dict", "value": {"kind": "dataclass", "name": "Item"}}},
        {"name": "count", "type": {"kind": "int"}},
        {"name": "label", "type": {"kind": "optional", "item": {"kind": "str"}}},
    ]
    assert description["functions"][1]["returns"] == {"kind": "list", "item": {"kind": "str"}}


def test_should_list_the_methods_without_static_methods(source_root):
    methods = TYPESCRIPT.members_of(TYPESCRIPT.default_runtime, source_root, source_root, "typed:Box").required

    assert methods == ("typed:Box.add", "typed:Box.names")


@pytest.mark.parametrize("target, message", [
    ("typed:total", "rest parameter"),
    ("typed:missing", "not exported"),
    ("nothing:f", "cannot find"),
])
def test_should_raise_when_the_target_cannot_be_described(source_root, target, message):
    with pytest.raises(TargetError, match=message):
        describe(source_root, target)


@pytest.mark.lean
def test_should_build_and_run_typescript_stubs_without_harness_errors(source_root):
    init_project(source_root, ".", ("typed:Box", "typed:double"), "typescript")
    config = load_config(source_root)

    scaffold_target(config, "typed:Box")
    scaffold_target(config, "typed:double", "Double")
    report = run_check(config)

    assert {finding.kind.label for finding in report.findings} == {"mismatch", "unused_mirror"}
