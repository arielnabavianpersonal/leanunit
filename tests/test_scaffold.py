import pytest

from nounit.config import load_config
from nounit.lock import Lock, load_lock
from nounit.scaffold import NOUNIT_LEAN, InitError, init_project


def test_should_make_a_project_that_loads(tmp_path):
    init_project(tmp_path, "src", ("pkg.mod:Thing",))

    config = load_config(tmp_path)
    assert config.cover == ("pkg.mod:Thing",)
    assert config.source_root == tmp_path / "src"
    assert load_lock(config.lock_path) == Lock()
    assert f'path = "{NOUNIT_LEAN}"' in (tmp_path / "lean" / "lakefile.toml").read_text()
    assert all((tmp_path / "lean" / name).is_dir() for name in ("Laws", "Model", "Proofs", "Gen"))


def test_should_not_overwrite_an_existing_project(tmp_path):
    (tmp_path / "nounit.toml").write_text("keep me")

    with pytest.raises(InitError, match="does not overwrite"):
        init_project(tmp_path, ".", ())
    assert (tmp_path / "nounit.toml").read_text() == "keep me"


def test_should_add_each_ignore_entry_once(tmp_path):
    (tmp_path / ".gitignore").write_text("dist/\n.nounit/\n")

    init_project(tmp_path, ".", ())

    assert (tmp_path / ".gitignore").read_text() == "dist/\n.nounit/\nlean/.lake/\nlean/NoUnitGenerated/\n"
