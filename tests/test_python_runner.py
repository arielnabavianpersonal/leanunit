import json
import subprocess
import sys

import pytest

from leanunit.languages import PYTHON_RUNNER as RUNNER_SCRIPT
from tests.sample_code import write_sample_module

EMPTY_BOX = {"items": {}, "tags": [], "note": None, "_count": 0}


def run(source_root, *requests):
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    completed = subprocess.run(
        [sys.executable, str(RUNNER_SCRIPT), "--source-root", str(source_root)],
        input=payload, capture_output=True, text=True, check=True,
    )
    *outcomes, coverage = [json.loads(line) for line in completed.stdout.splitlines()]
    return outcomes, coverage["coverage"]


@pytest.fixture
def source_root(tmp_path):
    return write_sample_module(tmp_path)


def test_should_return_the_object_and_the_value_when_a_method_succeeds(source_root):
    outcomes, _ = run(source_root, {"target": "sample_mod:Box.add", "args": [EMPTY_BOX, "k", 5]})

    assert outcomes == [{
        "self": {"items": {"k": {"name": "k", "value": 5}}, "tags": [], "note": None, "_count": 1},
        "return": 1,
    }]


def test_should_show_the_partial_change_when_a_method_raises(source_root):
    outcomes, _ = run(source_root, {"target": "sample_mod:Box.add_all", "args": [EMPTY_BOX, ["a", ""]]})

    assert outcomes == [{"raise": "ValueError", "self": {**EMPTY_BOX, "items": {"a": {"name": "a", "value": None}}}}]


def test_should_decode_nested_dataclasses_from_the_type_hints(source_root):
    box = {**EMPTY_BOX, "items": {"x": {"name": "first", "value": None}}}

    outcomes, _ = run(source_root, {"target": "sample_mod:Box.first_name", "args": [box]})

    assert outcomes[0]["return"] == "first"


def test_should_use_null_for_self_when_the_target_is_a_function(source_root):
    outcomes, _ = run(source_root, {"target": "sample_mod:double", "args": [3]})

    assert outcomes == [{"self": None, "return": 6}]


def test_should_keep_the_protocol_clean_when_the_code_prints(source_root):
    outcomes, _ = run(source_root, {"target": "sample_mod:Box.noisy", "args": [EMPTY_BOX]})

    assert outcomes == [{"self": EMPTY_BOX, "return": None}]


@pytest.mark.parametrize("request_body, message", [
    ({"target": "sample_mod:missing", "args": []}, "not a Python function"),
    ({"target": "no_such_module:f", "args": []}, "cannot find"),
    ({"target": "sample_mod:Box.noisy", "args": []}, "first argument must be the object"),
    ({"target": "sample_mod:double", "args": [{"__default__": True}]}, "has no default value"),
    ({"target": "sample_mod:looped", "args": []}, "contains itself"),
    ({"target": "sample_mod:size_of", "args": [{"__bytes__": "not base64!"}]}, "not base64"),
    ({"target": "sample_mod:broken", "args": []}, "cannot encode"),
    ({"target": "sample_mod:double", "args": [1, 2]}, "takes 1 arguments"),
    ({"target": "sample_mod:Box.add", "args": [{"extra": 1}, "k", 1]}, "no fields named"),
])
def test_should_answer_with_an_error_when_the_harness_cannot_call_the_target(source_root, request_body, message):
    outcomes, _ = run(source_root, request_body)

    assert message in outcomes[0]["error"]


def test_should_list_the_missing_lines_when_a_branch_never_runs(source_root):
    _, coverage = run(source_root, {"target": "sample_mod:double", "args": [3]})

    lines = (source_root / "sample_mod.py").read_text().splitlines()
    assert [lines[number - 1].strip() for number in coverage["sample_mod:double"]["missing"]] == ["return 0"]


def test_should_miss_no_lines_when_every_branch_runs(source_root):
    _, coverage = run(
        source_root,
        {"target": "sample_mod:double", "args": [3]},
        {"target": "sample_mod:double", "args": [-1]},
        {"target": "sample_mod:Box.add", "args": [EMPTY_BOX, "k", 1]},
        {"target": "sample_mod:Box.add", "args": [{**EMPTY_BOX, "items": {"k": {"name": "k"}}}, "k", 1]},
    )

    assert coverage == {
        "sample_mod:double": {"lines": 3, "missing": []},
        "sample_mod:Box.add": {"lines": 5, "missing": []},
    }


def test_should_pass_keyword_only_arguments_by_name(source_root):
    outcomes, _ = run(source_root, {"target": "sample_mod:window", "args": ["hello", 1, 3, ".", "> "]})

    assert outcomes == [{"self": None, "return": "> el"}]


METER = {"value": 3}


@pytest.mark.parametrize("request_body, outcome", [
    ({"target": "sample_mod:Meter.doubled", "args": [METER]}, {"self": METER, "return": 6}),
    ({"target": "sample_mod:Meter.__str__", "args": [METER]}, {"self": METER, "return": "3 m"}),
    ({"target": "sample_mod:Meter.zero", "args": []}, {"self": None, "return": {"value": 0}}),
    ({"target": "sample_mod:Box.make", "args": []}, {"self": None, "return": EMPTY_BOX}),
    ({"target": "sample_mod:Meter.__init__", "args": [{"__default__": True}]}, {"self": None, "return": {"value": 1}}),
    ({"target": "sample_mod:Meter.__init__", "args": [5]}, {"self": None, "return": {"value": 5}}),
])
def test_should_call_properties_dunders_classmethods_staticmethods_and_constructors(source_root, request_body, outcome):
    outcomes, _ = run(source_root, request_body)

    assert outcomes == [outcome]


@pytest.mark.parametrize("args, result", [
    (["a", {"__default__": True}, {"__default__": True}], "a-x"),
    (["a", {"__default__": True}, "y"], "a-y"),
    (["a", "+", "y"], "a+y"),
])
def test_should_use_the_default_value_when_the_model_leaves_out_an_argument(source_root, args, result):
    outcomes, _ = run(source_root, {"target": "sample_mod:joined", "args": args})

    assert outcomes == [{"self": None, "return": result}]


@pytest.mark.parametrize("request_body, result", [
    ({"target": "sample_mod:pack", "args": ["hi"]}, {"__bytes__": "aGk="}),
    ({"target": "sample_mod:size_of", "args": [{"__bytes__": "aGk="}]}, 2),
    ({"target": "sample_mod:paint", "args": [{"__enum__": "sample_mod:Color.RED"}]}, "red"),
    ({"target": "sample_mod:paint", "args": ["blue"]}, "blue"),
    ({"target": "sample_mod:favorite", "args": []}, {"__enum__": "sample_mod:Color.BLUE"}),
    ({"target": "sample_mod:make_plain", "args": [2]}, {"__class__": "sample_mod:Plain", "n": 2, "_seen": [2]}),
    ({"target": "sample_mod:plain_total", "args": [{"__class__": "sample_mod:Plain", "n": 4}]}, 4),
    ({"target": "sample_mod:unique", "args": [[3, 1, 3]]}, {"__set__": [1, 3]}),
    ({"target": "sample_mod:ratio", "args": [1, 0]}, {"__float__": "inf"}),
    ({"target": "sample_mod:ratio", "args": [1, 2]}, 0.5),
])
def test_should_encode_and_decode_values_that_json_does_not_have(source_root, request_body, result):
    outcomes, _ = run(source_root, request_body)

    assert outcomes == [{"self": None, "return": result}]


def test_should_measure_the_lines_of_a_watched_helper_through_its_callers(source_root):
    _, coverage = run(
        source_root,
        {"watch": "sample_mod:Meter._scale"},
        {"target": "sample_mod:Meter.doubled", "args": [METER]},
    )

    lines = (source_root / "sample_mod.py").read_text().splitlines()
    missing = [lines[number - 1].strip() for number in coverage["sample_mod:Meter._scale"]["missing"]]
    assert missing == ['raise ValueError("negative")']
