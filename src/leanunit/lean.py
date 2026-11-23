from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOTS = ("Laws", "Model", "Proofs", "Gen")
SAMPLER_IMPORT_ROOTS = ("Model", "Gen")
GENERATED_DIR = "LeanUnitGenerated"
AUDIT_MARKER = "LEANUNIT_AUDIT "
MAX_ARITY = 4
DEFAULT_MAX_SIZE = 12


class LeanError(Exception):
    def __init__(self, stage: str, log: str) -> None:
        super().__init__(f"Lean {stage} failed")
        self.stage = stage
        self.log = log


@dataclass(frozen=True)
class ProofInfo:
    name: str
    axioms: tuple[str, ...]


@dataclass(frozen=True)
class LawInfo:
    name: str
    module: str
    statement: str
    covers: tuple[str, ...]
    proofs: tuple[ProofInfo, ...]
    refutations: tuple[ProofInfo, ...]
    problem: str | None


@dataclass(frozen=True)
class MirrorInfo:
    name: str
    module: str
    target: str
    arity: int


@dataclass(frozen=True)
class ForbiddenInfo:
    name: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Audit:
    toolchain: str
    modules: tuple[str, ...]
    laws: tuple[LawInfo, ...]
    mirrors: tuple[MirrorInfo, ...]
    forbidden: tuple[ForbiddenInfo, ...]


@dataclass(frozen=True)
class Sample:
    target: str
    args: list[Any]
    expected: Any


def find_lake() -> str | None:
    on_path = shutil.which("lake")
    if on_path:
        return on_path
    elan_lake = Path.home() / ".elan" / "bin" / "lake"
    return str(elan_lake) if elan_lake.exists() else None


class LeanProject:
    def __init__(self, path: Path, lake: str | None = None) -> None:
        self._path = path
        self._lake = lake or find_lake() or "lake"

    @property
    def path(self) -> Path:
        return self._path

    def audit(self) -> Audit:
        modules = self._project_modules()
        self._run("build", [self._lake, "build", *modules])
        audit_file = self._write_generated("Audit.lean", _audit_source(modules))
        output = self._run("audit", [self._lake, "env", "lean", str(audit_file.relative_to(self._path))])
        return _parse_audit(output)

    def sample(self, audit: Audit, count: int, seed: int, max_size: int = DEFAULT_MAX_SIZE) -> tuple[Sample, ...]:
        if not audit.mirrors:
            return ()
        imports = [module for module in self._project_modules() if module.split(".")[0] in SAMPLER_IMPORT_ROOTS]
        sampler = self._write_generated("Conform.lean", _sampler_source(imports, audit.mirrors))
        output = self._run(
            "sampler",
            [self._lake, "env", "lean", "--run", str(sampler.relative_to(self._path)), str(count), str(seed), str(max_size)],
        )
        return tuple(_parse_sample(line) for line in output.splitlines() if line.strip())

    def _project_modules(self) -> list[str]:
        modules = []
        for root in PROJECT_ROOTS:
            base = self._path / root
            if base.is_dir():
                modules += [_module_name(self._path, file) for file in sorted(base.rglob("*.lean"))]
        return modules

    def _write_generated(self, file_name: str, text: str) -> Path:
        target = self._path / GENERATED_DIR / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text() != text:
            target.write_text(text)
        return target

    def _run(self, stage: str, command: list[str]) -> str:
        completed = subprocess.run(command, cwd=self._path, capture_output=True, text=True)
        if completed.returncode != 0:
            raise LeanError(stage, completed.stdout + completed.stderr)
        return completed.stdout


def _module_name(project: Path, file: Path) -> str:
    return ".".join(file.relative_to(project).with_suffix("").parts)


def _audit_source(modules: list[str]) -> str:
    return "\n".join(["import LeanUnit.Audit", *(f"import {module}" for module in modules), "", "#leanunit_audit", ""])


def _sampler_source(imports: list[str], mirrors: tuple[MirrorInfo, ...]) -> str:
    entries = [_sampler_entry(mirror) for mirror in mirrors]
    return "\n".join([
        "import LeanUnit",
        *(f"import {module}" for module in imports),
        "",
        "def leanunitMirrors : List LeanUnit.Mirror := [",
        ",\n".join(entries),
        "]",
        "",
        "def main (args : List String) : IO UInt32 := LeanUnit.conformMain leanunitMirrors args",
        "",
    ])


def _sampler_entry(mirror: MirrorInfo) -> str:
    if not 1 <= mirror.arity <= MAX_ARITY:
        raise LeanError(
            "sampler",
            f"mirror {mirror.name} has {mirror.arity} explicit arguments, but LeanUnit supports 1 to {MAX_ARITY}",
        )
    return f"  LeanUnit.Mirror.of{mirror.arity} {json.dumps(mirror.target)} {mirror.name}"


def _parse_audit(output: str) -> Audit:
    report_line = next((line for line in output.splitlines() if line.startswith(AUDIT_MARKER)), None)
    if report_line is None:
        raise LeanError("audit", output or "the audit printed no report")
    data = json.loads(report_line[len(AUDIT_MARKER):])
    return Audit(
        toolchain=data["toolchain"],
        modules=tuple(data["modules"]),
        laws=tuple(_parse_law(law) for law in data["laws"]),
        mirrors=tuple(
            MirrorInfo(name=m["name"], module=m["module"], target=m["target"], arity=m["arity"])
            for m in data["mirrors"]
        ),
        forbidden=tuple(ForbiddenInfo(name=f["name"], reasons=tuple(f["reasons"])) for f in data["forbidden"]),
    )


def _parse_law(law: dict[str, Any]) -> LawInfo:
    return LawInfo(
        name=law["name"],
        module=law["module"],
        statement=statement_hash(law["hashInput"]),
        covers=tuple(law["covers"]),
        proofs=tuple(_parse_proof(proof) for proof in law["proofs"]),
        refutations=tuple(_parse_proof(proof) for proof in law["refutations"]),
        problem=law.get("problem"),
    )


def _parse_proof(proof: dict[str, Any]) -> ProofInfo:
    return ProofInfo(name=proof["name"], axioms=tuple(proof["axioms"]))


def _parse_sample(line: str) -> Sample:
    data = json.loads(line)
    return Sample(target=data["target"], args=data["args"], expected=data["expected"])


def statement_hash(hash_input: str) -> str:
    return "sha256:" + hashlib.sha256(hash_input.encode()).hexdigest()
