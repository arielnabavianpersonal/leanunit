import pytest

from leanunit.config import ConfigError, load_config
from leanunit.languages import JAVASCRIPT, PYTHON, TYPESCRIPT
from leanunit.pycode import TargetError


def write(tmp_path, text):
    (tmp_path / "leanunit.toml").write_text(text)
    return tmp_path


@pytest.mark.parametrize("section, language", [("python", PYTHON), ("typescript", TYPESCRIPT), ("javascript", JAVASCRIPT)])
def test_should_pick_the_language_from_the_table_name(tmp_path, section, language):
    config = load_config(write(tmp_path, f'[{section}]\ncover = ["m:f"]\n'))

    assert config.language is language


def test_should_use_the_node_runtime_with_type_stripping_for_typescript(tmp_path):
    config = load_config(write(tmp_path, '[typescript]\ncover = ["m:f"]\n'))

    assert config.runtime == ("node", "--experimental-strip-types", "--no-warnings")


def test_should_accept_a_custom_runtime(tmp_path):
    config = load_config(write(tmp_path, '[javascript]\nruntime = ["/opt/node/bin/node"]\n'))

    assert config.runtime == ("/opt/node/bin/node",)


def test_should_refuse_two_language_tables(tmp_path):
    with pytest.raises(ConfigError, match="one language table"):
        load_config(write(tmp_path, "[python]\n[typescript]\n"))


def test_should_prefer_the_typescript_file_over_the_javascript_file(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "mod.js").write_text("")
    (tmp_path / "lib" / "mod.ts").write_text("")

    assert TYPESCRIPT.module_file(tmp_path, "lib/mod") == tmp_path / "lib" / "mod.ts"


def test_should_raise_when_no_file_has_a_known_suffix(tmp_path):
    (tmp_path / "mod.py").write_text("")

    with pytest.raises(TargetError, match="no .js/.mjs/.cjs file"):
        JAVASCRIPT.module_file(tmp_path, "mod")


def test_should_list_only_source_files_of_the_language(tmp_path):
    for name in ("a.ts", "b.py", "c.mjs"):
        (tmp_path / name).write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "d.ts").write_text("")

    assert sorted(path.name for path in TYPESCRIPT.source_files(tmp_path, tmp_path / "lean")) == ["a.ts", "c.mjs"]


def test_should_pass_the_language_to_the_node_runner(tmp_path):
    command = TYPESCRIPT.runner_command(TYPESCRIPT.default_runtime, tmp_path)

    assert command[-4:] == ["--source-root", str(tmp_path), "--language", "typescript"]
    assert command[-5].endswith("node_runner.mjs")
