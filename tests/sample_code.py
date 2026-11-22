SAMPLE_MODULE = '''
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Item:
    name: str
    value: Any = None


@dataclass
class Box:
    items: dict[str, Item] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    note: str | None = None
    _count: int = 0

    def add(self, key: str, value: Any) -> int:
        """Add one item."""
        if key in self.items:
            raise KeyError(key)
        self.items[key] = Item(key, value)
        self._count += 1
        return self._count

    def add_all(self, keys: list[str]) -> None:
        for key in keys:
            if not key:
                raise ValueError("empty key")
            self.items[key] = Item(key)

    def first_name(self) -> str | None:
        for item in self.items.values():
            return item.name
        return None

    def noisy(self) -> None:
        print("hello from the code")

    @classmethod
    def make(cls) -> "Box":
        return cls()


def double(n: int) -> int:
    if n < 0:
        return 0
    return n * 2


def broken() -> object:
    return object()
'''


def write_sample_module(root):
    (root / "sample_mod.py").write_text(SAMPLE_MODULE)
    return root
