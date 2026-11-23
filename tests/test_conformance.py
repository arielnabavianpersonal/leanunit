import sys

import pytest

from leanunit.config import Config
from leanunit.conformance import run_conformance, same
from leanunit.lean import Sample
from tests.sample_code import write_sample_module


@pytest.fixture
def config(tmp_path):
    write_sample_module(tmp_path)
    return Config(
        root=tmp_path, lean_project=tmp_path / "lean", python=(sys.executable,), source_root=tmp_path,
        cover=(), exclude=(), samples=10, seed=1, agent_command=(), agent_timeout_seconds=60,
    )


def double(n, result):
    return Sample(target="sample_mod:double", args=[n], expected={"self": None, "return": result})


@pytest.mark.parametrize("left, right, expected", [
    ({"a": [1, True]}, {"a": [1, True]}, True),
    ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
    (True, 1, False),
    (1, 1.0, False),
    ([1, 2], [2, 1], False),
    ({"a": None}, {}, False),
])
def test_should_compare_json_strictly(left, right, expected):
    assert same(left, right) is expected


def test_should_pass_when_the_model_and_the_code_agree(config):
    result = run_conformance(config, [double(2, 4), double(-5, 0)])

    assert (result.samples_run, result.mismatches, result.harness_errors) == (2, (), ())
    assert dict(result.missing_lines) == {}


def test_should_keep_the_smallest_mismatch_for_each_target(config):
    result = run_conformance(config, [double(123456, 1), double(7, 1), double(2, 4)])

    assert [(m.args, m.expected["return"], m.actual["return"]) for m in result.mismatches] == [([7], 1, 14)]
    assert dict(result.mismatch_counts) == {"sample_mod:double": 2}


def test_should_report_missing_lines_when_the_samples_skip_a_branch(config):
    result = run_conformance(config, [double(2, 4)])

    assert list(result.missing_lines) == ["sample_mod:double"]


def test_should_report_a_harness_error_instead_of_a_mismatch(config):
    result = run_conformance(config, [Sample(target="sample_mod:missing", args=[], expected=None)])

    assert result.mismatches == ()
    assert "not a Python function" in result.harness_errors[0]


def test_should_report_a_harness_error_when_the_interpreter_cannot_start(config):
    broken = Config(**{**config.__dict__, "python": ("/no/such/python",)})

    result = run_conformance(broken, [double(2, 4)])

    assert "did not run" in result.harness_errors[0]
