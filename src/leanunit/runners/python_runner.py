from __future__ import annotations

import argparse
import ast
import base64
import binascii
import contextlib
import dataclasses
import enum
import functools
import importlib
import inspect
import json
import math
import sys
import textwrap
import types
import typing
from typing import Any

SILENT_STATEMENTS = (ast.Global, ast.Nonlocal)
PRIMITIVES = {str: "str", int: "int", bool: "bool", float: "float", bytes: "bytes"}
POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
SUPPORTED_PARAMETERS = (*POSITIONAL, inspect.Parameter.KEYWORD_ONLY)
VALUE_DUNDERS = frozenset({
    "__str__", "__repr__", "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
    "__hash__", "__len__", "__bool__", "__contains__", "__getitem__",
})
CONSTRUCTOR = "__init__"
TAG_BYTES = "__bytes__"
TAG_FLOAT = "__float__"
TAG_ENUM = "__enum__"
TAG_SET = "__set__"
TAG_CALLABLE = "__callable__"
TAG_CLASS = "__class__"
TAG_DEFAULT = "__default__"
SINGLE_TAGS = frozenset({TAG_BYTES, TAG_FLOAT, TAG_ENUM, TAG_SET, TAG_CALLABLE})
SKIPPED_SLOTS = frozenset({"__dict__", "__weakref__"})


class HarnessError(Exception):
    pass


class Kind(enum.Enum):
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    CLASS_METHOD = "classmethod"
    STATIC_METHOD = "staticmethod"
    CONSTRUCTOR = "constructor"

    @property
    def has_receiver(self) -> bool:
        return self in (Kind.METHOD, Kind.PROPERTY)


@dataclasses.dataclass(frozen=True)
class Target:
    name: str
    kind: Kind
    function: types.FunctionType | None
    owner: type | None
    statement_lines: frozenset[int]
    code_objects: frozenset[types.CodeType]


def resolve(name: str) -> Target:
    holder, last = _holder(name)
    if isinstance(holder, type):
        kind, function = _class_member(name, holder, last)
        owner: type | None = holder
    else:
        kind, function, owner = Kind.FUNCTION, getattr(holder, last, None), None
        if not isinstance(function, types.FunctionType):
            raise HarnessError(f"{name} is not a Python function")
    lines = statement_lines(function) if function else frozenset()
    codes = nested_code_objects(function.__code__) if function else frozenset()
    return Target(name, kind, function, owner, lines, codes)


def _holder(name: str) -> tuple[Any, str]:
    module_name, _, qualname = name.partition(":")
    parts = qualname.split(".")
    try:
        holder: Any = importlib.import_module(module_name)
        for part in parts[:-1]:
            holder = getattr(holder, part)
    except (ImportError, AttributeError) as error:
        raise HarnessError(f"cannot find {name}: {error}") from error
    return holder, parts[-1]


def _class_member(name: str, owner: type, attribute: str) -> tuple[Kind, types.FunctionType | None]:
    member = owner.__dict__.get(attribute)
    if attribute == CONSTRUCTOR:
        post_init = owner.__dict__.get("__post_init__") if dataclasses.is_dataclass(owner) else member
        return Kind.CONSTRUCTOR, post_init if isinstance(post_init, types.FunctionType) and _has_source(post_init) else None
    if isinstance(member, property) and isinstance(member.fget, types.FunctionType):
        return Kind.PROPERTY, member.fget
    if isinstance(member, classmethod) and isinstance(member.__func__, types.FunctionType):
        return Kind.CLASS_METHOD, member.__func__
    if isinstance(member, staticmethod) and isinstance(member.__func__, types.FunctionType):
        return Kind.STATIC_METHOD, member.__func__
    if isinstance(member, types.FunctionType):
        return Kind.METHOD, member
    raise HarnessError(f"{name} is not a function, a method, a property, a classmethod, or a staticmethod")


def _has_source(function: types.FunctionType) -> bool:
    try:
        inspect.getsourcelines(function)
    except (OSError, TypeError):
        return False
    return True


def statement_lines(function: types.FunctionType) -> frozenset[int]:
    try:
        source, first_line = inspect.getsourcelines(function)
    except (OSError, TypeError):
        return frozenset()
    node = ast.parse(textwrap.dedent("".join(source))).body[0]
    body = node.body[1:] if _is_docstring(node.body[0]) else node.body
    lines = {
        inner.lineno + first_line - 1
        for statement in body
        for inner in ast.walk(statement)
        if isinstance(inner, ast.stmt) and _makes_code(inner)
    }
    return frozenset(lines)


def _is_docstring(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(
        statement.value.value, str
    )


def _makes_code(statement: ast.stmt) -> bool:
    if isinstance(statement, SILENT_STATEMENTS) or _is_docstring(statement):
        return False
    return not (isinstance(statement, ast.AnnAssign) and statement.value is None)


def nested_code_objects(code: types.CodeType) -> frozenset[types.CodeType]:
    found = {code}
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            found |= nested_code_objects(constant)
    return frozenset(found)


class LineRecorder:
    def __init__(self) -> None:
        self._owners: dict[types.CodeType, str] = {}
        self.hits: dict[str, set[int]] = {}

    def watch(self, target: Target) -> None:
        self.hits.setdefault(target.name, set())
        for code in target.code_objects:
            self._owners[code] = target.name

    def trace(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        owner = self._owners.get(frame.f_code)
        if owner is None:
            return None
        hits = self.hits[owner]

        def record(frame: types.FrameType, event: str, arg: Any) -> Any:
            if event == "line":
                hits.add(frame.f_lineno)
            return record

        return record


def hints_for(subject: Any) -> dict[str, Any]:
    try:
        return typing.get_type_hints(subject)
    except Exception:
        return _hints_one_at_a_time(subject)


def _hints_one_at_a_time(subject: Any) -> dict[str, Any]:
    module = sys.modules.get(getattr(subject, "__module__", ""), None)
    namespace = vars(module) if module else {}
    hints = {}
    for name, annotation in getattr(subject, "__annotations__", {}).items():
        try:
            hints[name] = eval(annotation, namespace) if isinstance(annotation, str) else annotation
        except Exception:
            hints[name] = Any
    return hints


def qualified_name(subject: Any) -> str:
    function = getattr(subject, "__func__", subject)
    return f"{getattr(function, '__module__', '?')}:{getattr(function, '__qualname__', type(subject).__qualname__)}"


def find_object(path: str) -> Any:
    holder, last = _holder(path)
    try:
        return getattr(holder, last)
    except AttributeError as error:
        raise HarnessError(f"cannot find {path}: {error}") from error


def decode(hint: Any, value: Any) -> Any:
    tagged, found = _decode_tag(value)
    if found:
        return tagged
    if value is None:
        return None
    if hint is Any or isinstance(hint, (str, typing.ForwardRef)):
        return _decode_any(value)
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return _decode_dataclass(hint, value)
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return _decode_enum_value(hint, value)
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        options = [option for option in args if option is not type(None)]
        return decode(options[0], value) if len(options) == 1 else _decode_any(value)
    if origin is list:
        return [decode(args[0] if args else Any, item) for item in value]
    if origin is tuple:
        item_hints = [args[0]] * len(value) if len(args) == 2 and args[1] is Ellipsis else list(args)
        return tuple(decode(item_hint, item) for item_hint, item in zip(item_hints, value))
    if origin in (set, frozenset):
        return origin(decode(args[0] if args else Any, item) for item in value)
    if origin is dict:
        value_hint = args[1] if len(args) == 2 else Any
        return {key: decode(value_hint, item) for key, item in value.items()}
    return _decode_any(value)


def _decode_any(value: Any) -> Any:
    tagged, found = _decode_tag(value)
    if found:
        return tagged
    if isinstance(value, dict):
        return {key: _decode_any(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_any(item) for item in value]
    return value


def _decode_tag(value: Any) -> tuple[Any, bool]:
    if not isinstance(value, dict):
        return None, False
    if TAG_CLASS in value:
        return _decode_object(value), True
    if len(value) != 1:
        return None, False
    tag, payload = next(iter(value.items()))
    if tag not in SINGLE_TAGS:
        return None, False
    return _decode_single(tag, payload), True


def _decode_single(tag: str, payload: Any) -> Any:
    if tag == TAG_SET:
        if not isinstance(payload, list):
            raise HarnessError("a set must be a JSON array")
        return {_decode_any(item) for item in payload}
    if not isinstance(payload, str):
        raise HarnessError(f"the value of {tag} must be a string")
    if tag == TAG_BYTES:
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as error:
            raise HarnessError(f"{payload!r} is not base64: {error}") from error
    if tag == TAG_FLOAT:
        try:
            return float(payload)
        except ValueError as error:
            raise HarnessError(f"{payload!r} is not a float") from error
    if tag == TAG_ENUM:
        owner, _, member = payload.rpartition(".")
        enum_type = find_object(owner)
        try:
            return enum_type[member]
        except (KeyError, TypeError) as error:
            raise HarnessError(f"{payload} is not an enum member") from error
    return find_object(payload)


def _decode_object(value: dict[str, Any]) -> Any:
    cls = find_object(value[TAG_CLASS])
    if not isinstance(cls, type):
        raise HarnessError(f"{value[TAG_CLASS]} is not a class")
    try:
        instance = cls.__new__(cls)
    except TypeError as error:
        raise HarnessError(f"LeanUnit cannot make an empty {cls.__name__}: {error}") from error
    for attribute, item in value.items():
        if attribute != TAG_CLASS:
            object.__setattr__(instance, attribute, _decode_any(item))
    return instance


def _decode_enum_value(enum_type: type, value: Any) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise HarnessError(f"{value!r} is not a value of {enum_type.__name__}") from error


def _decode_dataclass(cls: type, value: Any) -> Any:
    if not isinstance(value, dict):
        raise HarnessError(f"{cls.__name__} needs a JSON object, but got {type(value).__name__}")
    fields = {field.name: field for field in dataclasses.fields(cls)}
    unknown = sorted(set(value) - set(fields))
    if unknown:
        raise HarnessError(f"{cls.__name__} has no fields named {unknown}")
    hints = hints_for(cls)
    decoded = {name: decode(hints.get(name, Any), item) for name, item in value.items() if not is_default(item)}
    instance = cls(**{name: item for name, item in decoded.items() if fields[name].init})
    for name, item in decoded.items():
        if not fields[name].init:
            object.__setattr__(instance, name, item)
    return instance


def is_default(value: Any) -> bool:
    return isinstance(value, dict) and value == {TAG_DEFAULT: True}


def encode(value: Any) -> Any:
    return _encode(value, frozenset())


def _encode(value: Any, path: frozenset[int]) -> Any:
    if isinstance(value, enum.Enum):
        return {TAG_ENUM: f"{qualified_name(type(value))}.{value.name}"}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {TAG_FLOAT: repr(value)}
    if isinstance(value, (bytes, bytearray)):
        return {TAG_BYTES: base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType, types.MethodType, type, functools.partial)):
        return {TAG_CALLABLE: qualified_name(value.func if isinstance(value, functools.partial) else value)}
    if id(value) in path:
        raise HarnessError("LeanUnit cannot encode a value that contains itself")
    inner = path | {id(value)}
    if dataclasses.is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name), inner) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise HarnessError("LeanUnit can encode a dict only when its keys are strings")
        return {key: _encode(item, inner) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item, inner) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_encode(item, inner) for item in value]
        return {TAG_SET: sorted(items, key=lambda item: json.dumps(item, sort_keys=True))}
    state = _object_state(value)
    if state is None:
        raise HarnessError(f"LeanUnit cannot encode a value of type {type(value).__name__}")
    return {TAG_CLASS: qualified_name(type(value)), **{key: _encode(item, inner) for key, item in state.items()}}


def _object_state(value: Any) -> dict[str, Any] | None:
    slots = _slot_names(type(value))
    if not hasattr(value, "__dict__") and not slots:
        return None
    state = dict(vars(value)) if hasattr(value, "__dict__") else {}
    state.update({slot: getattr(value, slot) for slot in slots if hasattr(value, slot)})
    return state


def _slot_names(cls: type) -> list[str]:
    names: list[str] = []
    for base in cls.__mro__:
        slots = base.__dict__.get("__slots__", ())
        names += [slots] if isinstance(slots, str) else list(slots)
    return [name for name in names if name not in SKIPPED_SLOTS]


def parameters_of(target: Target) -> list[inspect.Parameter]:
    if target.kind is Kind.CONSTRUCTOR:
        return list(inspect.signature(target.owner).parameters.values())
    parameters = list(inspect.signature(target.function).parameters.values())
    if target.kind in (Kind.METHOD, Kind.PROPERTY, Kind.CLASS_METHOD):
        return parameters[1:]
    return parameters


def hints_of(target: Target) -> dict[str, Any]:
    if target.kind is Kind.CONSTRUCTOR:
        hints = hints_for(target.owner) if dataclasses.is_dataclass(target.owner) else {}
        return {**hints, **hints_for(target.owner.__init__)}
    return hints_for(target.function)


def bind(parameters: list[inspect.Parameter], hints: dict[str, Any], args: list[Any]) -> tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    skipped = False
    for parameter, arg in zip(parameters, args):
        if is_default(arg):
            if parameter.default is inspect.Parameter.empty:
                raise HarnessError(f"{parameter.name} has no default value, so the model cannot leave it out")
            skipped = True
            continue
        value = decode(hints.get(parameter.name, Any), arg)
        if parameter.kind in POSITIONAL and not skipped:
            positional.append(value)
        elif parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise HarnessError(f"{parameter.name} is positional-only, so the model cannot leave out an argument before it")
        else:
            keyword[parameter.name] = value
    return positional, keyword


def invoker(target: Target, receiver: Any) -> Any:
    if target.kind is Kind.CONSTRUCTOR:
        return target.owner
    if target.kind is Kind.CLASS_METHOD:
        return functools.partial(target.function, target.owner)
    if target.kind.has_receiver:
        return functools.partial(target.function, receiver)
    return target.function


def call(target: Target, args: list[Any], recorder: LineRecorder) -> dict[str, Any]:
    parameters = parameters_of(target)
    receiver = None
    if target.kind.has_receiver:
        if not args:
            raise HarnessError(f"{target.name} is a method, so its first argument must be the object")
        receiver = decode(target.owner, args[0])
        args = args[1:]
    if len(args) != len(parameters):
        raise HarnessError(f"{target.name} takes {len(parameters)} arguments, but the model sent {len(args)}")
    positional, keyword = bind(parameters, hints_of(target), args)
    function = invoker(target, receiver)
    sys.settrace(recorder.trace)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = function(*positional, **keyword)
    except Exception as error:
        sys.settrace(None)
        return {"raise": type(error).__name__, "self": encode(receiver)}
    sys.settrace(None)
    return {"self": encode(receiver), "return": encode(result)}


def serve(lines: typing.Iterable[str], out: typing.TextIO) -> None:
    targets: dict[str, Target | HarnessError] = {}
    recorder = LineRecorder()
    for line in lines:
        if not line.strip():
            continue
        request = json.loads(line)
        if "watch" in request:
            _known(request["watch"], targets, recorder)
            continue
        out.write(json.dumps(_answer(request, targets, recorder)) + "\n")
    coverage = {
        name: {
            "lines": len(target.statement_lines),
            "missing": sorted(target.statement_lines - recorder.hits.get(name, set())),
        }
        for name, target in targets.items()
        if isinstance(target, Target)
    }
    out.write(json.dumps({"coverage": coverage}) + "\n")


def _known(name: str, targets: dict[str, Target | HarnessError], recorder: LineRecorder) -> Target | HarnessError:
    if name not in targets:
        try:
            targets[name] = resolve(name)
            recorder.watch(targets[name])
        except HarnessError as error:
            targets[name] = error
    return targets[name]


def _answer(request: dict[str, Any], targets: dict[str, Target | HarnessError], recorder: LineRecorder) -> dict[str, Any]:
    target = _known(request["target"], targets, recorder)
    if isinstance(target, HarnessError):
        return {"error": str(target)}
    try:
        return call(target, request["args"], recorder)
    except HarnessError as error:
        return {"error": str(error)}


def describe(name: str) -> dict[str, Any]:
    holder, last = _holder(name)
    member = holder.__dict__.get(last) if isinstance(holder, type) else getattr(holder, last, None)
    types_seen: dict[str, Any] = {}
    if isinstance(member, type):
        owner, names = member, [f"{name}.{attribute}" for attribute in class_members(member)]
    elif isinstance(holder, type):
        owner, names = holder, [name]
    elif isinstance(member, types.FunctionType):
        owner, names = None, [name]
    else:
        raise HarnessError(f"{name} is not a class or a Python function")
    targets = [resolve(target) for target in names]
    if owner is not None and not dataclasses.is_dataclass(owner) and any(target.kind.has_receiver for target in targets):
        raise HarnessError(f"{owner.__name__} is not a dataclass, and LeanUnit supports methods and properties of dataclasses only")
    owner_tree = type_tree(owner, types_seen) if owner is not None and dataclasses.is_dataclass(owner) else None
    return {
        "target": name,
        "owner": owner_tree,
        "functions": [_describe_function(target, types_seen) for target in targets],
        "types": types_seen,
    }


def class_members(owner: type) -> list[str]:
    names = [
        attribute
        for attribute, value in owner.__dict__.items()
        if _function_of(value) is not None
        and _written_in_source(_function_of(value), owner)
        and is_public_member(attribute)
    ]
    if dataclasses.is_dataclass(owner) and _has_defaults(owner):
        names.append(CONSTRUCTOR)
    return names


def _function_of(value: Any) -> types.FunctionType | None:
    if isinstance(value, property):
        value = value.fget
    elif isinstance(value, (classmethod, staticmethod)):
        value = value.__func__
    return value if isinstance(value, types.FunctionType) else None


def _has_defaults(owner: type) -> bool:
    fields = dataclasses.fields(owner)
    defaulted = any(
        field.default is not dataclasses.MISSING or field.default_factory is not dataclasses.MISSING for field in fields
    )
    return defaulted or "__post_init__" in owner.__dict__


def is_public_member(name: str) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return name in VALUE_DUNDERS
    return not name.startswith("_")


def _written_in_source(function: types.FunctionType, owner: type) -> bool:
    try:
        return function.__code__.co_filename == inspect.getsourcefile(owner)
    except TypeError:
        return False


def _describe_function(target: Target, types_seen: dict[str, Any]) -> dict[str, Any]:
    parameters = parameters_of(target)
    unsupported = [parameter.name for parameter in parameters if parameter.kind not in SUPPORTED_PARAMETERS]
    if unsupported:
        raise HarnessError(f"{target.name} has parameters {unsupported} that take a variable number of arguments")
    hints = hints_of(target)
    returns = target.owner if target.kind is Kind.CONSTRUCTOR else hints.get("return", Any)
    return {
        "target": target.name,
        "name": target.name.partition(":")[2].rsplit(".", 1)[-1],
        "kind": target.kind.value,
        "receiver": target.kind.has_receiver,
        "params": [
            {
                "name": parameter.name,
                "type": type_tree(hints.get(parameter.name, Any), types_seen),
                "default": parameter.default is not inspect.Parameter.empty,
            }
            for parameter in parameters
        ],
        "returns": type_tree(returns, types_seen),
    }


def type_tree(hint: Any, types_seen: dict[str, Any]) -> dict[str, Any]:
    if hint is type(None) or hint is None:
        return {"kind": "none"}
    if hint in PRIMITIVES:
        return {"kind": PRIMITIVES[hint]}
    if hint is list:
        return {"kind": "list", "item": {"kind": "any"}}
    if hint is dict:
        return {"kind": "dict", "value": {"kind": "any"}}
    if isinstance(hint, type) and issubclass(hint, enum.Enum) and len(hint) > 0:
        if hint.__name__ not in types_seen:
            types_seen[hint.__name__] = {"enum": qualified_name(hint), "members": [member.name for member in hint]}
        return {"kind": "enum", "name": hint.__name__}
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        if hint.__name__ not in types_seen:
            types_seen[hint.__name__] = {"fields": []}
            field_hints = hints_for(hint)
            types_seen[hint.__name__]["fields"] = [
                {"name": field.name, "type": type_tree(field_hints.get(field.name, Any), types_seen)}
                for field in dataclasses.fields(hint)
            ]
        return {"kind": "dataclass", "name": hint.__name__}
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        options = [option for option in args if option is not type(None)]
        if len(options) == 1 and len(args) == 2:
            return {"kind": "optional", "item": type_tree(options[0], types_seen)}
        return {"kind": "any"}
    if origin is list:
        return {"kind": "list", "item": type_tree(args[0] if args else Any, types_seen)}
    if origin is dict and (not args or args[0] is str):
        return {"kind": "dict", "value": type_tree(args[1] if len(args) == 2 else Any, types_seen)}
    return {"kind": "any"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LeanUnit Python runner")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--describe", metavar="TARGET")
    options = parser.parse_args(argv)
    sys.path.insert(0, options.source_root)
    protocol = sys.stdout
    if options.describe:
        try:
            answer = describe(options.describe)
        except HarnessError as error:
            answer = {"error": str(error)}
        protocol.write(json.dumps(answer) + "\n")
        return 0
    serve(sys.stdin, protocol)
    protocol.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
