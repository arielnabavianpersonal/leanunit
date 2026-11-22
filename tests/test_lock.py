import json

import pytest

from nounit.lock import LawApproval, Lock, LockError, load_lock, lock_to_json, save_lock

APPROVAL = LawApproval(statement="sha256:abc", covers=("m:f",), approved_by="dev@example.com", approved_at="2026-11-22")


def test_should_return_an_empty_lock_when_the_file_is_missing(tmp_path):
    assert load_lock(tmp_path / "nounit.lock") == Lock()


def test_should_keep_the_original_lock_when_approving():
    original = Lock()

    updated = original.approve("Laws.a", APPROVAL)

    assert dict(original.laws) == {}
    assert dict(updated.laws) == {"Laws.a": APPROVAL}


def test_should_drop_a_law_when_removing():
    assert dict(Lock().approve("Laws.a", APPROVAL).remove("Laws.a").laws) == {}


def test_should_round_trip_through_the_file(tmp_path):
    lock = Lock().with_toolchain("4.36.0").approve("Laws.a", APPROVAL)

    save_lock(tmp_path / "nounit.lock", lock)

    assert load_lock(tmp_path / "nounit.lock") == lock


def test_should_write_sorted_camel_case_json():
    text = lock_to_json(Lock().with_toolchain("4.36.0").approve("Laws.b", APPROVAL).approve("Laws.a", APPROVAL))

    assert json.loads(text) == {
        "lockfileVersion": 1,
        "leanToolchain": "4.36.0",
        "laws": {
            name: {"statement": "sha256:abc", "covers": ["m:f"], "approvedBy": "dev@example.com", "approvedAt": "2026-11-22"}
            for name in ("Laws.a", "Laws.b")
        },
    }
    assert text.index('"Laws.a"') < text.index('"Laws.b"')
    assert text.endswith("\n")


@pytest.mark.parametrize("text", ["not json", '{"lockfileVersion": 2}'])
def test_should_raise_when_the_file_is_invalid(tmp_path, text):
    (tmp_path / "nounit.lock").write_text(text)

    with pytest.raises(LockError):
        load_lock(tmp_path / "nounit.lock")
