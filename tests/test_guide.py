from leanunit.guide import GUIDE_FILE, POINTER, guide_text, write_guide


def test_should_start_with_the_guide_title():
    assert guide_text().startswith("# LeanUnit guide\n")


def test_should_write_the_guide_and_create_agents_md(tmp_path):
    written = write_guide(tmp_path)

    assert {path.name for path in written} == {GUIDE_FILE, "AGENTS.md"}
    assert (tmp_path / GUIDE_FILE).read_text() == guide_text()
    assert (tmp_path / "AGENTS.md").read_text() == POINTER
    assert not (tmp_path / "CLAUDE.md").exists()


def test_should_append_the_pointer_once_to_existing_agent_files(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Team rules\n")
    (tmp_path / "CLAUDE.md").write_text("Be brief.")

    write_guide(tmp_path)
    second = write_guide(tmp_path)

    assert second == ()
    assert (tmp_path / "AGENTS.md").read_text() == "# Team rules\n\n" + POINTER
    assert (tmp_path / "CLAUDE.md").read_text() == "Be brief.\n\n" + POINTER
