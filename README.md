# NoUnit

NoUnit replaces hand-written unit tests with Lean proofs.
A lock file records the laws that a human approved, as `package-lock.json` records versions.
The build fails when a change breaks a law, and an agent repairs the proofs.

## How it works

You approve **laws**. A law is a Lean statement that your code must obey, for example "an inactive state never saves an invocation-scoped approval".
An agent writes the rest:

- a **model**, which is a copy of the logic of your code in Lean
- **generators**, which make random inputs for the model
- **proofs**, which the Lean kernel verifies

A model is not your code. Thus, NoUnit runs the model and your real code on the same random inputs and compares the outputs.
NoUnit also makes sure that the samples execute each line of the code.
This comparison is the conformance step. It ties the proofs to the code that you ship.

## Requirements

- Lean 4 through [elan](https://github.com/leanprover/elan). The Lean projects pin `leanprover/lean4:v4.36.0`.
- Python 3.11 or later for NoUnit. NoUnit has no run-time dependencies.
- An interpreter that can import your code. NoUnit uses its own interpreter if you do not set one.

NoUnit runs the Lean sampler with `lean --run`, so it does not need a C compiler.

## Install

NoUnit is not on PyPI yet. Install it from a clone:

```bash
uv tool install --editable /path/to/nounit
```

## Quick start

1. Make the files: `nounit init --source-root src --cover mypackage.module:MyClass`.
2. Set an agent command in the `[agent]` table of `nounit.toml`.
3. Run `nounit fix`. The agent writes a model, generators, draft laws, and proofs.
4. Read each draft law in `lean/Laws/`.
5. Approve the laws that you agree with: `nounit approve <law>`.
6. Add `nounit check` to your build.

## Project layout

| Path | Owner | Contents |
|---|---|---|
| `nounit.toml` | Team | The code to cover, the Lean project, the sample count, and the agent command. |
| `nounit.lock` | Human | The approved laws. Only `nounit approve` writes this file. |
| `lean/Laws/` | Human | The laws. An agent can write drafts. |
| `lean/Model/` | Agent | The model functions, each with `@[mirror "module:Qualname"]`. |
| `lean/Gen/` | Agent | The `Sample` instances for the model types. |
| `lean/Proofs/` | Agent | One theorem for each law, or a refutation with `¬`. |

## Commands

| Command | What it does |
|---|---|
| `nounit check` | Verifies the laws, the proofs, and the conformance. It exits with 1 when it finds a problem. |
| `nounit check --json` | Prints the same report as JSON. |
| `nounit approve <law>...` | Records the current statement of each law in the lock. Short names are permitted. |
| `nounit approve --all` | Approves all laws, and removes laws that are gone. |
| `nounit fix` | Starts the agent when the check fails. Then it restores the protected files and checks again. |
| `nounit init` | Makes `nounit.toml`, an empty lock, and the Lean project. |

## What the check verifies

`nounit check` passes only when all these conditions are true:

- Each law is approved, and its statement agrees with the lock.
- Each law has a proof, and no law has a refutation.
- No proof uses `sorry` or an axiom other than `propext`, `Classical.choice`, and `Quot.sound`.
- No definition that a law or a mirror uses has `implemented_by`, `extern`, `unsafe`, or `partial`.
- Each mirror gives the same JSON output as its Python function on all samples.
- The samples execute each line of each mirrored Python function.
- Each function in the `cover` list has a mirror, and a law uses each mirror.

## The lock file

The lock records a hash for each law.
The hash covers the law and each helper definition that the law uses.
A change to a mirrored function does not change the hash, because conformance ties that function to the real code.
Thus, an agent can repair a proof without approval, but it cannot weaken a law without approval.

## Write a model

A model function mirrors one Python function or method.
For a method, the first argument is the object, and the result is a `NoUnit.Outcome`:

```lean
@[mirror "strands.interrupt:_InterruptState.activate"]
def activate (s : State) : Outcome State Unit :=
  .ok { s with activated := true, _version := s._version + 1 } ()
```

- `Outcome.ok self ret` is a normal return. `Outcome.raise "KeyError" self` is an exception.
- `NoUnit.Val` holds any JSON value, for example a field of type `Any`.
- `NoUnit.Dict α` is a Python `dict[str, T]`.
- The JSON form of each model type must agree with the Python value. Use field names that agree with the Python names.

## Example

`examples/strands-interrupt` covers the `_InterruptState` class of the Strands Agents SDK.
It has 10 laws. NoUnit proves 9 of them, and it refutes 1 of them.
The refuted law shows a real bug: `resume` can change the state without an increase of the version.
Refer to `examples/strands-interrupt/README.md`.

## Limits

- Version 1 supports Python only. TypeScript is next, with the same protocol and a new runner.
- Version 1 supports pure logic only. It does not support I/O, async code, threads, floats, or callbacks.
- Conformance is random testing. A model can differ from the code on inputs that the samples do not include.
- Version 1 does not shrink a failure. It shows the smallest failure that it found.

Refer to `docs/design.md` for the full design.
