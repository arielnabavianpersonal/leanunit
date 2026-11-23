# LeanUnit version 1 implementation plan

> **For agentic workers:** Use superpowers:executing-plans to do this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build LeanUnit version 1 as specified in `docs/design.md`, and run it on the `_InterruptState` example.

**Architecture:** A Python command (`leanunit`) controls a Lean library (`LeanUnit`). Lean does the audit and makes the conformance samples. A small Python runner calls the real code. The Python core compares the outcomes, reads and writes the lock, and starts the agent.

**Tech stack:** Lean 4.36.0 with Lake, Python 3.11 or later with only the standard library at run time, pytest, and uv.

---

## File structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | The package, the `leanunit` entry point, and the pytest group. |
| `src/leanunit/cli.py` | The commands `init`, `check`, `approve`, and `fix`, and their exit codes. |
| `src/leanunit/config.py` | `Config` and `load_config(root)`, from `leanunit.toml`. |
| `src/leanunit/lock.py` | `Lock`, `LawApproval`, `load_lock`, and `save_lock`. |
| `src/leanunit/lean.py` | `LeanProject`: the build, `audit()`, and `sample(audit, count, seed)`. It writes the generated files. |
| `src/leanunit/pycode.py` | `methods_of(source_root, target)`, from the Python AST. |
| `src/leanunit/conformance.py` | `run_conformance(config, samples)`: the runner process, the strict JSON comparison, and the coverage. |
| `src/leanunit/report.py` | `Finding`, `FindingKind`, `LawStatus`, and `Report`, with text and JSON output. |
| `src/leanunit/check.py` | `run_check(config, lean)`: all the pass conditions of the design. |
| `src/leanunit/approve.py` | `run_approve(...)`: it writes the current hashes into the lock. |
| `src/leanunit/fix.py` | `run_fix(...)`: the agent process and the file guard. |
| `src/leanunit/scaffold.py` | `init_project(root)`: the files for a new project. |
| `src/leanunit/AGENT.md` | The instructions that `fix` sends to the agent. |
| `src/leanunit/runners/python_runner.py` | The Python runner. It uses only the standard library. |
| `src/leanunit/lean/LeanUnit/*.lean` | The Lean library: `Attr`, `Val`, `Dict`, `Outcome`, `Gen`, `Mirror`, and `Audit`. |
| `tests/` | The pytest tests and a small Lean fixture project for the audit. |
| `examples/strands-interrupt/` | The copy of `interrupt.py` and its Lean project. |

## Task 1: The Lean library

**Files:** `src/leanunit/lean/lakefile.toml`, `lean-toolchain`, `LeanUnit.lean`, `LeanUnit/{Attr,Val,Dict,Outcome,Gen,Mirror,Audit}.lean`.

- [x] `Attr`: the tag attribute `@[law]` and the attribute `@[mirror "module:Qualname"]` with a string parameter.
- [x] `Val`: a JSON value type with `DecidableEq`, `ToJson`, and `FromJson`. It has no floats.
- [x] `Dict α`: a list of key and value pairs with unique keys. It has `empty`, `get?`, `insert`, `filter`, `keys`, and lemmas for `filter` and `insert`. It converts to a JSON object.
- [x] `Outcome σ ρ`: `ok self ret` or `raise exc self`, with the JSON forms of the design.
- [x] `Gen` and `Sample α`: a random generator with a size, and instances for `Nat`, `Int`, `Bool`, `String`, `List`, `Option`, `Prod`, `Val`, and `Dict`.
- [x] `Mirror`: `Mirror.of1` to `Mirror.of4`, and `conformMain mirrors args`, which writes one JSON line for each sample.
- [x] `Audit`: the command `#leanunit_audit`. It writes one line `LEANUNIT_AUDIT <json>` with the laws, proofs, refutations, axioms, hash inputs, covered targets, mirrors, and forbidden constants.
- [x] Verify: `lake build` passes in `src/leanunit/lean`.
- [x] Commit.

## Task 2: The audit fixture and its test

**Files:** `tests/fixtures/lean-mini/`, `tests/test_lean_audit.py`.

- [x] Make a small fixture project. It has these six cases:
  - a proved law
  - a refuted law
  - a proof with `sorry`
  - a proof with a new axiom
  - a mirror
  - a constant with `@[implemented_by]`
- [x] Test that the audit gives the correct status for each law.
- [x] Test that the hash changes when a helper of a law changes.
- [x] Test that the hash stays the same when a mirrored function changes or when blank lines move the law.
- [x] Verify: `uv run pytest tests/test_lean_audit.py` passes.
- [x] Commit.

## Task 3: Config, lock, and Python code analysis

**Files:** `src/leanunit/config.py`, `lock.py`, `pycode.py`, and their tests.

- [x] Test and write `load_config`. Defaults: the interpreter of LeanUnit, 300 samples, seed 1, and no agent.
- [x] Test and write the lock. A missing file is an empty lock. `approve` returns a new lock. The file is JSON with sorted keys.
- [x] Test and write `methods_of`. A class target gives each method in the class body. A function target gives itself.
- [x] Verify: `uv run pytest` passes.
- [x] Commit.

## Task 4: The Python runner and conformance

**Files:** `src/leanunit/runners/python_runner.py`, `conformance.py`, and their tests.

- [x] Test and write the decoder from type hints, the encoder, and the two outcome forms of the runner.
- [x] Test that the runner shows a partial change before an exception, a harness error, and the missing lines.
- [x] Test and write `run_conformance`. The comparison is strict, so `true` is not equal to `1`. LeanUnit keeps the smallest mismatch for each target.
- [x] Verify: `uv run pytest` passes.
- [x] Commit.

## Task 5: Check, approve, fix, init, and the command line

**Files:** `report.py`, `check.py`, `approve.py`, `fix.py`, `scaffold.py`, `cli.py`, `AGENT.md`, and their tests.

- [x] Test `run_check` with a fake `LeanProject`. Each condition of the design must give its finding.
- [x] Test `run_approve`. It writes the hashes and the covered targets, it removes laws that are gone, and it stops when `LEANUNIT_AGENT` is set.
- [x] Test `run_fix` with a fake agent script. The agent receives the report, the guard restores a protected file, and the second check runs.
- [x] Test `init_project`. It writes the files and does not overwrite a file.
- [x] Verify: `uv run pytest` passes.
- [x] Commit.

## Task 6: The example

**Files:** `examples/strands-interrupt/{leanunit.toml,leanunit.lock,README.md}` and `lean/{Laws,Model,Gen,Proofs}/Interrupt.lean`.

- [x] Write the model of `activate`, `deactivate`, `end_tool_cycle`, `end_interrupt_cycle`, `resume`, `set_pending_tool_results`, `to_dict`, and `_get_version`.
- [x] Write the laws of the design, and one law for each mirror.
- [x] Write the generators, the proofs, and the refutation of the version law.
- [x] Verify: `leanunit check` shows only unapproved laws and the refuted law. In a copy, `leanunit approve --all` leaves only the refuted law.
- [x] Commit.

## Task 7: The agent loop and the documents

- [x] Change a function in a copy of the example, run `leanunit fix` with `claude -p`, and record the result.
- [x] Write `README.md`.
- [x] Verify: `uv run pytest` passes, with the integration tests.
- [x] Commit.
