import pytest

from leanunit.pycode import Members, TargetError, members_of

SOURCE = """
class Machine:
    def start(self):
        pass

    async def stop(self):
        pass

    VALUE = 1

    def __eq__(self, other):
        return True

    def __init__(self):
        pass

    @property
    def speed(self):
        return 1

    @speed.setter
    def speed(self, value):
        pass

    @classmethod
    def build(cls):
        return cls()

    def _reset(self):
        pass

    def __enter__(self):
        return self


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


def test_should_require_public_methods_and_value_dunders_when_the_target_is_a_class(source_root):
    members = members_of(source_root, "pkg.mod:Machine")

    assert members.required == (
        "pkg.mod:Machine.start",
        "pkg.mod:Machine.stop",
        "pkg.mod:Machine.__eq__",
        "pkg.mod:Machine.speed",
        "pkg.mod:Machine.build",
    )


def test_should_list_private_methods_as_helpers_when_the_target_is_a_class(source_root):
    assert members_of(source_root, "pkg.mod:Machine").helpers == ("pkg.mod:Machine._reset",)


def test_should_return_the_target_when_it_is_a_function(source_root):
    assert members_of(source_root, "pkg.mod:helper") == Members(("pkg.mod:helper",))


def test_should_read_the_package_init_when_the_module_is_a_package(source_root):
    assert members_of(source_root, "pkg:top") == Members(("pkg:top",))


@pytest.mark.parametrize("target", ["pkg.mod:Missing", "pkg.nothing:helper", "pkg.mod"])
def test_should_raise_when_the_target_does_not_exist(source_root, target):
    with pytest.raises(TargetError):
        members_of(source_root, target)
