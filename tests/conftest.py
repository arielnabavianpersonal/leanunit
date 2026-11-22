import shutil
from pathlib import Path

import pytest

from nounit.lean import find_lake

REPO = Path(__file__).parents[1]
NOUNIT_LEAN = REPO / "src" / "nounit" / "lean"
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config, items):
    if find_lake():
        return
    skip = pytest.mark.skip(reason="lake is not installed")
    for item in items:
        if "lean" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def copy_lean_project(tmp_path):
    def copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(FIXTURES / name, target, ignore=shutil.ignore_patterns(".lake", "NoUnitGenerated", "lake-manifest.json"))
        lakefile = target / "lakefile.toml"
        lakefile.write_text(lakefile.read_text().replace('path = "../../../src/nounit/lean"', f'path = "{NOUNIT_LEAN}"'))
        return target

    return copy
