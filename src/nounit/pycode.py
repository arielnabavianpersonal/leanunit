from __future__ import annotations

import ast
from pathlib import Path

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


class TargetError(Exception):
    pass


def split_target(target: str) -> tuple[str, str]:
    module, separator, qualname = target.partition(":")
    if not separator or not module or not qualname:
        raise TargetError(f"target {target!r} must have the form module:Qualname")
    return module, qualname


def module_file(source_root: Path, module: str) -> Path:
    base = source_root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    raise TargetError(f"module {module!r} has no file under {source_root}")


def methods_of(source_root: Path, target: str) -> tuple[str, ...]:
    module, qualname = split_target(target)
    node = _find(ast.parse(module_file(source_root, module).read_text()), qualname, target)
    if isinstance(node, ast.ClassDef):
        return tuple(f"{module}:{qualname}.{item.name}" for item in node.body if isinstance(item, FUNCTION_NODES))
    return (target,)


def _find(tree: ast.Module, qualname: str, target: str) -> ast.AST:
    scope: list[ast.stmt] = tree.body
    found: ast.AST | None = None
    for part in qualname.split("."):
        found = next(
            (node for node in scope if isinstance(node, (ast.ClassDef, *FUNCTION_NODES)) and node.name == part),
            None,
        )
        if found is None:
            raise TargetError(f"target {target!r} does not exist")
        scope = found.body
    return found
