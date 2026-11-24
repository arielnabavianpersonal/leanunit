SAMPLE_MODULE = '''
import enum
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


def window(text: str, start: int, *, end: int, fill: str, label: str) -> str:
    if end < start:
        raise ValueError("end is before start")
    return label + text[start:end].ljust(end - start, fill[:1] or " ")


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


@dataclass
class Meter:
    value: int = 1

    @property
    def doubled(self) -> int:
        return self._scale(2)

    def _scale(self, factor: int) -> int:
        if factor < 0:
            raise ValueError("negative")
        return self.value * factor

    def __str__(self) -> str:
        return f"{self.value} m"

    @staticmethod
    def zero() -> "Meter":
        return Meter(0)


class Plain:
    def __init__(self, n: int) -> None:
        self.n = n
        self._seen = [n]


def make_plain(n: int) -> Plain:
    return Plain(n)


def plain_total(item: Any) -> int:
    return item.n


def joined(first: str, sep: str = "-", last: str = "x") -> str:
    return first + sep + last


def pack(text: str) -> bytes:
    return text.encode()


def size_of(data: bytes) -> int:
    return len(data)


def paint(color: Color) -> str:
    return color.value


def favorite() -> Color:
    return Color.BLUE


def unique(items: list[int]) -> set[int]:
    return set(items)


def ratio(top: int, bottom: int) -> float:
    return top / bottom if bottom else float("inf")


def looped() -> list:
    items: list = []
    items.append(items)
    return items
'''


def write_sample_module(root):
    (root / "sample_mod.py").write_text(SAMPLE_MODULE)
    return root
