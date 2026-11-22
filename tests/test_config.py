import sys

import pytest

from nounit.config import DEFAULT_SAMPLES, ConfigError, load_config


def write(tmp_path, text):
    (tmp_path / "nounit.toml").write_text(text)
    return tmp_path


def test_should_use_defaults_when_only_cover_is_set(tmp_path):
    config = load_config(write(tmp_path, '[python]\ncover = ["pkg.mod:Thing"]\n'))

    assert config.cover == ("pkg.mod:Thing",)
    assert config.python == (sys.executable,)
    assert config.samples == DEFAULT_SAMPLES
    assert config.lean_project == tmp_path / "lean"
    assert config.agent_command == ()
    assert config.lock_path == tmp_path / "nounit.lock"


def test_should_read_every_section_when_all_are_set(tmp_path):
    config = load_config(write(tmp_path, """
[python]
interpreter = "python3.12"
source_root = "src"
cover = ["a.b:C"]
exclude = ["a.b:C.skip"]

[lean]
project = "spec"

[conformance]
samples = 50
seed = 7

[agent]
command = ["claude", "-p"]
timeout_seconds = 60
"""))

    assert config.python == ("python3.12",)
    assert config.source_root == tmp_path / "src"
    assert config.exclude == ("a.b:C.skip",)
    assert config.lean_project == tmp_path / "spec"
    assert (config.samples, config.seed) == (50, 7)
    assert config.agent_command == ("claude", "-p")
    assert config.agent_timeout_seconds == 60


def test_should_raise_when_the_file_is_missing(tmp_path):
    with pytest.raises(ConfigError, match="nounit init"):
        load_config(tmp_path)


@pytest.mark.parametrize("text", [
    '[python]\ncover = ["no_colon"]\n',
    '[conformance]\nsamples = 0\n',
    '[agent]\ncommand = 3\n',
    'python = 1\n',
])
def test_should_raise_when_a_value_is_invalid(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))
