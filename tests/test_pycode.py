import pytest

from leanunit.pycode import TargetError, methods_of

SOURCE = """
class Machine:
    def start(self):
        pass

    async def stop(self):
        pass

    VALUE = 1

    def __eq__(self, other):
        return True


def helper(x):
    return x
"""


@pytest.fixture
def source_root(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("def top():\n    return 1\n")
    (package / "mod.py").write_text(SOURCE)
    return tmp_path


def test_should_list_each_method_when_the_target_is_a_class(source_root):
    assert methods_of(source_root, "pkg.mod:Machine") == ("pkg.mod:Machine.start", "pkg.mod:Machine.stop")


def test_should_return_the_target_when_it_is_a_function(source_root):
    assert methods_of(source_root, "pkg.mod:helper") == ("pkg.mod:helper",)


def test_should_read_the_package_init_when_the_module_is_a_package(source_root):
    assert methods_of(source_root, "pkg:top") == ("pkg:top",)


@pytest.mark.parametrize("target", ["pkg.mod:Missing", "pkg.nothing:helper", "pkg.mod"])
def test_should_raise_when_the_target_does_not_exist(source_root, target):
    with pytest.raises(TargetError):
        methods_of(source_root, target)
