from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leanunit.config import Config
from leanunit.pycode import TargetError, split_target

LEAN_PRIMITIVES = {"str": "String", "int": "Int", "bool": "Bool", "float": "Val", "none": "Unit", "any": "Val"}
LEAN_KEYWORDS = frozenset({
    "Prop", "Sort", "Type", "abbrev", "at", "attribute", "axiom", "break", "builtin_initialize", "by",
    "calc", "catch", "class", "continue", "decreasing_by", "def", "deriving", "do", "elab", "else",
    "end", "example", "export", "extends", "finally", "for", "forall", "from", "fun", "have", "hiding",
    "if", "import", "in", "include", "inductive", "infix", "infixl", "infixr", "initialize", "instance",
    "let", "local", "macro", "macro_rules", "match", "mut", "mutual", "namespace", "nofun", "nomatch",
    "noncomputable", "notation", "obtain", "omit", "opaque", "open", "partial", "postfix", "prefix",
    "private", "protected", "renaming", "return", "scoped", "section", "set_option", "show", "structure",
    "suffices", "syntax", "termination_by", "then", "theorem", "try", "universe", "unless", "unsafe",
    "variable", "where", "with",
})
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_']*\Z")
MAX_ARGUMENTS = 8
NOT_IMPLEMENTED = "NotImplementedError"
DERIVING = "deriving DecidableEq, Repr, ToJson, FromJson"


class StubError(Exception):
    pass


@dataclass(frozen=True)
class StubResult:
    name: str
    created: tuple[Path, ...]
    mirrors: tuple[str, ...]
    in_cover_list: bool


def scaffold_target(config: Config, target: str, name: str | None = None) -> StubResult:
    described = describe_target(config, target)
    description = {
        **described,
        "functions": [function for function in described["functions"] if function["target"] not in config.exclude],
    }
    module_name = name or default_name(target, description)
    if not IDENTIFIER.match(module_name):
        raise StubError(f"{module_name!r} is not a valid Lean module name")
    files = {config.lean_project / path: text for path, text in render_files(module_name, description).items()}
    existing = [str(path) for path in files if path.exists()]
    if existing:
        raise StubError(f"LeanUnit does not overwrite files. These already exist: {', '.join(existing)}")
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return StubResult(
        name=module_name,
        created=tuple(files),
        mirrors=tuple(function["target"] for function in description["functions"]),
        in_cover_list=_in_cover_list(config, target),
    )


def describe_target(config: Config, target: str) -> dict[str, Any]:
    try:
        return config.language.describe(config.runtime, config.source_root, config.root, target)
    except TargetError as error:
        raise StubError(str(error)) from error


def default_name(target: str, description: dict[str, Any]) -> str:
    module, qualname = split_target(target)
    base = qualname.split(".")[0] if description["owner"] else module.rsplit(".", 1)[-1]
    words = [word for word in re.split(r"[^A-Za-z0-9]+", base) if word]
    name = "".join(word[:1].upper() + word[1:] for word in words) or "Target"
    return name if name[0].isalpha() else f"T{name}"


def render_files(name: str, description: dict[str, Any]) -> dict[Path, str]:
    type_names = {type_name: lean_name(type_name) for type_name in description["types"]}
    ordered = _dependency_order(description["types"])
    return {
        Path("Model") / f"{name}.lean": _model_file(name, description, ordered, type_names),
        Path("Gen") / f"{name}.lean": _gen_file(name, description, ordered, type_names),
        Path("Laws") / f"{name}.lean": _module(f"Model.{name}", f"LeanUnit Model.{name}", f"Laws.{name}", []),
        Path("Proofs") / f"{name}.lean": _module(f"Laws.{name}", f"LeanUnit Model.{name}", f"Proofs.{name}", []),
    }


def lean_name(name: str) -> str:
    return name if IDENTIFIER.match(name) and name not in LEAN_KEYWORDS else f"«{name}»"


def lean_type(tree: dict[str, Any], type_names: dict[str, str]) -> str:
    kind = tree["kind"]
    if kind in LEAN_PRIMITIVES:
        return LEAN_PRIMITIVES[kind]
    if kind == "dataclass":
        return type_names[tree["name"]]
    wrapper = {"list": "List", "dict": "Dict", "optional": "Option"}[kind]
    inner = tree["value"] if kind == "dict" else tree["item"]
    return f"({wrapper} {lean_type(inner, type_names)})"


def _dependency_order(types: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(type_name: str) -> None:
        if type_name in ordered or type_name in visiting:
            return
        visiting.add(type_name)
        for field in types[type_name]["fields"]:
            for dependency in _dataclasses_in(field["type"]):
                visit(dependency)
        visiting.discard(type_name)
        ordered.append(type_name)

    for type_name in types:
        visit(type_name)
    return ordered


def _dataclasses_in(tree: dict[str, Any]) -> list[str]:
    if tree["kind"] == "dataclass":
        return [tree["name"]]
    inner = tree.get("item") or tree.get("value")
    return _dataclasses_in(inner) if inner else []


def _model_file(name: str, description: dict[str, Any], ordered: list[str], type_names: dict[str, str]) -> str:
    owner = description["owner"]
    structures = [_structure(type_name, description["types"][type_name], type_names) for type_name in ordered]
    stubs = [_mirror_stub(function, owner, type_names) for function in description["functions"]]
    return _module("LeanUnit", "Lean LeanUnit", f"Model.{name}", [*structures, *stubs])


def _structure(type_name: str, shape: dict[str, Any], type_names: dict[str, str]) -> str:
    fields = [f"  {lean_name(field['name'])} : {lean_type(field['type'], type_names)}" for field in shape["fields"]]
    return "\n".join([f"structure {type_names[type_name]} where", *fields, DERIVING])


def _mirror_stub(function: dict[str, Any], owner: dict[str, Any] | None, type_names: dict[str, str]) -> str:
    arguments = len(function["params"]) + (1 if owner else 0)
    if not 1 <= arguments <= MAX_ARGUMENTS:
        raise StubError(
            f"{function['target']} takes {arguments} arguments, but LeanUnit supports 1 to {MAX_ARGUMENTS}, the object included"
        )
    binders = [f"(self : {lean_type(owner, type_names)})"] if owner else []
    binders += [f"({lean_name(param['name'])} : {lean_type(param['type'], type_names)})" for param in function["params"]]
    state = lean_type(owner, type_names) if owner else "Unit"
    receiver = "self" if owner else "()"
    returns = lean_type(function["returns"], type_names)
    return "\n".join([
        f'@[mirror "{function["target"]}"]',
        f"def {lean_name(function['name'])} {' '.join(binders)} : Outcome {state} {returns} :=",
        f'  .raise "{NOT_IMPLEMENTED}" {receiver}',
    ])


def _gen_file(name: str, description: dict[str, Any], ordered: list[str], type_names: dict[str, str]) -> str:
    instances = [_sample_instance(type_names[type_name], description["types"][type_name]) for type_name in ordered]
    return _module(f"Model.{name}", f"Lean LeanUnit Model.{name}", f"Gen.{name}", instances)


def _sample_instance(lean_type_name: str, shape: dict[str, Any]) -> str:
    fields = ", ".join(f"{lean_name(field['name'])} := ← Sample.sample" for field in shape["fields"])
    return f"instance : Sample {lean_type_name} :=\n  ⟨do pure {{ {fields} }}⟩"


def _module(imported: str, opened: str, namespace: str, declarations: list[str]) -> str:
    body = "\n\n".join(declarations)
    parts = [f"import {imported}", "", f"open {opened}", "", f"namespace {namespace}", ""]
    if body:
        parts += [body, ""]
    parts += [f"end {namespace}", ""]
    return "\n".join(parts)


def _in_cover_list(config: Config, target: str) -> bool:
    module, qualname = split_target(target)
    owner = f"{module}:{qualname.split('.')[0]}"
    return target in config.cover or owner in config.cover
