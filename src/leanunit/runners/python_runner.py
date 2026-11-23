from __future__ import annotations

import argparse
import ast
import contextlib
import dataclasses
import importlib
import inspect
import json
import sys
import textwrap
import types
import typing
from typing import Any

UNSUPPORTED_MEMBERS = (staticmethod, classmethod, property)
SILENT_STATEMENTS = (ast.Global, ast.Nonlocal)
PRIMITIVES = {str: "str", int: "int", bool: "bool", float: "float"}
POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


class HarnessError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Target:
    name: str
    function: types.FunctionType
    owner: type | None
    statement_lines: frozenset[int]
    code_objects: frozenset[types.CodeType]


def resolve(name: str) -> Target:
    module_name, _, qualname = name.partition(":")
    try:
        holder: Any = importlib.import_module(module_name)
        parts = qualname.split(".")
        for part in parts[:-1]:
            holder = getattr(holder, part)
    except (ImportError, AttributeError) as error:
        raise HarnessError(f"cannot find {name}: {error}") from error
    owner = holder if isinstance(holder, type) else None
    member = holder.__dict__.get(parts[-1]) if owner else getattr(holder, parts[-1], None)
    if isinstance(member, UNSUPPORTED_MEMBERS):
        raise HarnessError(f"{name} is a {type(member).__name__}, but LeanUnit supports plain methods and functions")
    if not isinstance(member, types.FunctionType):
        raise HarnessError(f"{name} is not a Python function")
    return Target(name, member, owner, statement_lines(member), nested_code_objects(member.__code__))


def statement_lines(function: types.FunctionType) -> frozenset[int]:
    source, first_line = inspect.getsourcelines(function)
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


def decode(hint: Any, value: Any) -> Any:
    if value is None or hint is Any or isinstance(hint, (str, typing.ForwardRef)):
        return value
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return _decode_dataclass(hint, value)
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        options = [option for option in args if option is not type(None)]
        return decode(options[0], value) if len(options) == 1 else value
    if origin is list:
        return [decode(args[0] if args else Any, item) for item in value]
    if origin is tuple:
        item_hints = [args[0]] * len(value) if len(args) == 2 and args[1] is Ellipsis else list(args)
        return tuple(decode(item_hint, item) for item_hint, item in zip(item_hints, value))
    if origin is dict:
        value_hint = args[1] if len(args) == 2 else Any
        return {key: decode(value_hint, item) for key, item in value.items()}
    return value


def _decode_dataclass(cls: type, value: Any) -> Any:
    if not isinstance(value, dict):
        raise HarnessError(f"{cls.__name__} needs a JSON object, but got {type(value).__name__}")
    fields = {field.name: field for field in dataclasses.fields(cls)}
    unknown = sorted(set(value) - set(fields))
    if unknown:
        raise HarnessError(f"{cls.__name__} has no fields named {unknown}")
    hints = hints_for(cls)
    decoded = {name: decode(hints.get(name, Any), item) for name, item in value.items()}
    instance = cls(**{name: item for name, item in decoded.items() if fields[name].init})
    for name, item in decoded.items():
        if not fields[name].init:
            object.__setattr__(instance, name, item)
    return instance


def encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: encode(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise HarnessError("LeanUnit can encode a dict only when its keys are strings")
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    raise HarnessError(f"LeanUnit cannot encode a value of type {type(value).__name__}")


def call(target: Target, args: list[Any], recorder: LineRecorder) -> dict[str, Any]:
    parameters = list(inspect.signature(target.function).parameters.values())
    hints = hints_for(target.function)
    if target.owner is not None:
        if not args:
            raise HarnessError(f"{target.name} is a method, so its first argument must be the object")
        receiver = decode(target.owner, args[0])
        parameters, args = parameters[1:], args[1:]
    else:
        receiver = None
    if len(args) != len(parameters):
        raise HarnessError(f"{target.name} takes {len(parameters)} arguments, but the model sent {len(args)}")
    decoded = [decode(hints.get(parameter.name, Any), arg) for parameter, arg in zip(parameters, args)]
    call_args = [receiver, *decoded] if target.owner is not None else decoded
    sys.settrace(recorder.trace)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = target.function(*call_args)
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


def _answer(request: dict[str, Any], targets: dict[str, Target | HarnessError], recorder: LineRecorder) -> dict[str, Any]:
    name = request["target"]
    if name not in targets:
        try:
            targets[name] = resolve(name)
            recorder.watch(targets[name])
        except HarnessError as error:
            targets[name] = error
    target = targets[name]
    if isinstance(target, HarnessError):
        return {"error": str(target)}
    try:
        return call(target, request["args"], recorder)
    except HarnessError as error:
        return {"error": str(error)}


def describe(name: str) -> dict[str, Any]:
    module_name, _, qualname = name.partition(":")
    try:
        holder: Any = importlib.import_module(module_name)
        parts = qualname.split(".")
        for part in parts[:-1]:
            holder = getattr(holder, part)
        member = holder.__dict__.get(parts[-1]) if isinstance(holder, type) else getattr(holder, parts[-1], None)
    except (ImportError, AttributeError) as error:
        raise HarnessError(f"cannot find {name}: {error}") from error
    types_seen: dict[str, Any] = {}
    if isinstance(member, type):
        owner, functions = member, [
            (f"{name}.{attribute}", value)
            for attribute, value in member.__dict__.items()
            if isinstance(value, types.FunctionType) and not _is_dunder(attribute) and _written_in_source(value, member)
        ]
    elif isinstance(holder, type) and isinstance(member, types.FunctionType):
        owner, functions = holder, [(name, member)]
    elif isinstance(member, types.FunctionType):
        owner, functions = None, [(name, member)]
    else:
        raise HarnessError(f"{name} is not a class or a Python function")
    if owner is not None and not dataclasses.is_dataclass(owner):
        raise HarnessError(f"{owner.__name__} is not a dataclass, and LeanUnit supports methods of dataclasses only")
    owner_tree = type_tree(owner, types_seen) if owner is not None else None
    return {
        "target": name,
        "owner": owner_tree,
        "functions": [_describe_function(target, function, owner is not None, types_seen) for target, function in functions],
        "types": types_seen,
    }


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _written_in_source(function: types.FunctionType, owner: type) -> bool:
    try:
        return function.__code__.co_filename == inspect.getsourcefile(owner)
    except TypeError:
        return False


def _describe_function(target: str, function: types.FunctionType, is_method: bool, types_seen: dict[str, Any]) -> dict[str, Any]:
    parameters = list(inspect.signature(function).parameters.values())
    if is_method:
        parameters = parameters[1:]
    unsupported = [parameter.name for parameter in parameters if parameter.kind not in POSITIONAL]
    if unsupported:
        raise HarnessError(f"{target} has parameters {unsupported} that are not positional")
    hints = hints_for(function)
    return {
        "target": target,
        "name": function.__name__,
        "params": [{"name": parameter.name, "type": type_tree(hints.get(parameter.name, Any), types_seen)} for parameter in parameters],
        "returns": type_tree(hints.get("return", Any), types_seen),
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
