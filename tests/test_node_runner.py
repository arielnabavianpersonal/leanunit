import json
import subprocess

import pytest

from leanunit.languages import JAVASCRIPT, TYPESCRIPT
from tests.sample_node import write_node_samples

pytestmark = pytest.mark.node

EMPTY_BOX = {"items": {}, "count": 0}


def run(language, source_root, *requests):
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    completed = subprocess.run(
        language.runner_command(language.default_runtime, source_root),
        input=payload, capture_output=True, text=True, check=True,
    )
    *outcomes, coverage = [json.loads(line) for line in completed.stdout.splitlines()]
    return outcomes, coverage["coverage"]


@pytest.fixture
def source_root(tmp_path):
    return write_node_samples(tmp_path)


def test_should_return_the_object_and_the_value_when_a_method_succeeds(source_root):
    outcomes, _ = run(JAVASCRIPT, source_root, {"target": "box:Box.add", "args": [EMPTY_BOX, "k", 5]})

    assert outcomes == [{"self": {"items": {"k": {"name": "k", "value": 5}}, "count": 1}, "return": 1}]


def test_should_show_the_state_and_the_error_class_when_a_method_throws(source_root):
    box = {"items": {"k": {"name": "k", "value": 1}}, "count": 1}

    outcomes, _ = run(JAVASCRIPT, source_root, {"target": "box:Box.add", "args": [box, "k", 2]})

    assert outcomes == [{"raise": "RangeError", "self": box}]


def test_should_await_an_async_method(source_root):
    box = {"items": {"a": {"name": "a", "value": 1}}, "count": 1}

    outcomes, _ = run(JAVASCRIPT, source_root, {"target": "box:Box.rename", "args": [box, "a", "b"]})

    assert outcomes == [{"self": {"items": {"b": {"name": "b", "value": 1}}, "count": 1}, "return": "b"}]


def test_should_keep_the_protocol_clean_when_the_code_logs(source_root):
    outcomes, _ = run(JAVASCRIPT, source_root, {"target": "box:Box.noisy", "args": [EMPTY_BOX]})

    assert outcomes == [{"self": EMPTY_BOX, "return": None}]


@pytest.mark.parametrize("request_body, message", [
    ({"target": "box:missing", "args": []}, "not an exported function"),
    ({"target": "box:Box.missing", "args": [EMPTY_BOX]}, "not a plain method"),
    ({"target": "nothing:f", "args": []}, "cannot find"),
    ({"target": "box:Box.callback", "args": [EMPTY_BOX]}, "cannot encode a value of type function"),
    ({"target": "box:Box.add", "args": [[], "k", 1]}, "needs a JSON object"),
])
def test_should_answer_with_an_error_when_the_harness_cannot_call_the_target(source_root, request_body, message):
    outcomes, _ = run(JAVASCRIPT, source_root, request_body)

    assert message in outcomes[0]["error"]


def test_should_list_the_missing_lines_when_a_branch_never_runs(source_root):
    _, coverage = run(JAVASCRIPT, source_root, {"target": "box:double", "args": [3]})

    lines = (source_root / "box.mjs").read_text().splitlines()
    assert [lines[number - 1].strip() for number in coverage["box:double"]["missing"]] == ["return 0;"]


def test_should_run_typescript_with_type_stripping(source_root):
    outcomes, coverage = run(
        TYPESCRIPT, source_root,
        {"target": "typed:double", "args": [3]},
        {"target": "typed:double", "args": [-1]},
    )

    assert outcomes == [{"self": None, "return": 6}, {"self": None, "return": 0}]
    assert coverage["typed:double"]["missing"] == []
