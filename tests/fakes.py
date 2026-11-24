from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from leanunit.config import Config
from leanunit.languages import PYTHON
from leanunit.lean import Audit, ForbiddenInfo, LawInfo, LeanError, MirrorInfo, ProofInfo, Sample

PROVED = ProofInfo(name="Proofs.double_positive_holds", axioms=("propext",))
MIRROR = MirrorInfo(name="Model.double", module="Model.Main", target="sample_mod:double", arity=1)
SAMPLES = (
    Sample(target="sample_mod:double", args=[2], expected={"self": None, "return": 4}),
    Sample(target="sample_mod:double", args=[-1], expected={"self": None, "return": 0}),
)


def law(
    name: str = "Laws.Main.double_positive",
    statement: str = "sha256:a",
    covers: tuple[str, ...] = ("sample_mod:double",),
    proofs: tuple[ProofInfo, ...] = (PROVED,),
    refutations: tuple[ProofInfo, ...] = (),
    problem: str | None = None,
) -> LawInfo:
    return LawInfo(name, "Laws.Main", statement, covers, proofs, refutations, problem)


def audit(
    *laws: LawInfo,
    mirrors: tuple[MirrorInfo, ...] = (MIRROR,),
    forbidden: tuple[ForbiddenInfo, ...] = (),
    toolchain: str = "4.36.0",
) -> Audit:
    return Audit(toolchain, ("Laws.Main", "Model.Main"), laws, mirrors, forbidden)


@dataclass
class FakeLean:
    result: Audit | None = None
    samples: tuple[Sample, ...] = SAMPLES
    audit_error: LeanError | None = None
    sample_error: LeanError | None = None

    def audit(self) -> Audit:
        if self.audit_error:
            raise self.audit_error
        assert self.result is not None
        return self.result

    def sample(self, audit: Audit, count: int, seed: int) -> tuple[Sample, ...]:
        if self.sample_error:
            raise self.sample_error
        return self.samples


def make_config(root: Path, **overrides) -> Config:
    import sys

    values = dict(
        root=root, lean_project=root / "lean", language=PYTHON, runtime=(sys.executable,), source_root=root,
        cover=("sample_mod:double",), exclude=(), samples=10, seed=1, agent_command=(), agent_timeout_seconds=60,
    )
    values.update(overrides)
    return Config(**values)
