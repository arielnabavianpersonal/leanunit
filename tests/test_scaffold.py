import pytest

from leanunit.config import load_config
from leanunit.lock import Lock, load_lock
from leanunit.scaffold import LEANUNIT_LEAN, InitError, init_project


def test_should_make_a_project_that_loads(tmp_path):
    init_project(tmp_path, "src", ("pkg.mod:Thing",))

    config = load_config(tmp_path)
    assert config.cover == ("pkg.mod:Thing",)
    assert config.source_root == tmp_path / "src"
    assert load_lock(config.lock_path) == Lock()
    assert f'path = "{LEANUNIT_LEAN}"' in (tmp_path / "lean" / "lakefile.toml").read_text()
    assert all((tmp_path / "lean" / name).is_dir() for name in ("Laws", "Model", "Proofs", "Gen"))
    assert (tmp_path / "LEANUNIT.md").read_text().startswith("# LeanUnit guide")
    assert "LEANUNIT.md" in (tmp_path / "AGENTS.md").read_text()


def test_should_not_overwrite_an_existing_project(tmp_path):
    (tmp_path / "leanunit.toml").write_text("keep me")

    with pytest.raises(InitError, match="does not overwrite"):
        init_project(tmp_path, ".", ())
    assert (tmp_path / "leanunit.toml").read_text() == "keep me"


def test_should_add_each_ignore_entry_once(tmp_path):
    (tmp_path / ".gitignore").write_text("dist/\n.leanunit/\n")

    init_project(tmp_path, ".", ())

    assert (tmp_path / ".gitignore").read_text() == "dist/\n.leanunit/\nlean/.lake/\nlean/LeanUnitGenerated/\n"
