import os
import shutil
import subprocess
from pathlib import Path

import pytest

from leanunit.lean import find_lake

REPO = Path(__file__).parents[1]
LEANUNIT_LEAN = REPO / "src" / "leanunit" / "lean"
FIXTURES = Path(__file__).parent / "fixtures"


def typescript_available() -> bool:
    if os.environ.get("LEANUNIT_TYPESCRIPT"):
        return True
    probe = subprocess.run(["node", "-e", "require.resolve('typescript')"], capture_output=True, check=False)
    return probe.returncode == 0


def pytest_collection_modifyitems(config, items):
    missing = {
        "lean": None if find_lake() else "lake is not installed",
        "node": None if shutil.which("node") else "node is not installed",
        "typescript": None if shutil.which("node") and typescript_available() else "the typescript package is not available",
    }
    for item in items:
        for marker, reason in missing.items():
            if reason and marker in item.keywords:
                item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def copy_lean_project(tmp_path):
    def copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(FIXTURES / name, target, ignore=shutil.ignore_patterns(".lake", "LeanUnitGenerated", "lake-manifest.json"))
        lakefile = target / "lakefile.toml"
        lakefile.write_text(lakefile.read_text().replace('path = "../../../src/leanunit/lean"', f'path = "{LEANUNIT_LEAN}"'))
        return target

    return copy
