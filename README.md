![LeanUnit: delete your unit tests](docs/images/hero.png)

# LeanUnit

LeanUnit replaces hand-written unit tests with Lean proofs.
A lock file records the laws that a human approved, as `package-lock.json` records versions.
The build fails when a change breaks a law.
A human, a personal agent, a workspace agent, or a CI job can then repair the proofs with the same commands.

## How it works

You approve **laws**. A law is a Lean statement that your code must obey, for example "an inactive state never saves an invocation-scoped approval".
A human or any agent writes the rest:

- a **model**, which is a copy of the logic of your code in Lean
- **generators**, which make random inputs for the model
- **proofs**, which the Lean kernel verifies

A model is not your code. Thus, LeanUnit runs the model and your real code on the same random inputs and compares the outputs.
LeanUnit also makes sure that the samples execute each line of the code.
This comparison is the conformance step. It ties the proofs to the code that you ship.

## LeanUnit and unit tests

Unit tests verify the inputs that you select. A LeanUnit law states a property for each input.

This function has a bug:

```python
def apply(state, answers):
    for id, value in answers:
        if id not in state.items:
            raise KeyError(id)
        state.items[id] = value
    state.version += 1
```

These unit tests pass:

```python
def test_bumps_version():
    s = State(items={"a": None}, version=0)
    apply(s, [("a", "yes")])
    assert s.version == 1

def test_unknown_id_raises():
    s = State(items={"a": None}, version=0)
    with pytest.raises(KeyError):
        apply(s, [("missing", "x")])
```

But the input `[("a", "yes"), ("missing", "x")]` writes `"yes"`, then raises `KeyError`, and does not increment the version.
No test uses this input, so no test fails.

In LeanUnit, a human approves one law:

```lean
@[law] def bump_on_change : Prop :=
  ∀ s answers, (apply s answers).self ≠ s → (apply s answers).self.version > s.version
```

No proof of this law is possible. An agent proves that the law is false with the input above, and the Lean kernel verifies that refutation.
`leanunit check` then reports `refuted_law`.
The corrected code validates all the answers before it writes. For that code, the law has a proof for each state and each list of answers.

| | Unit tests | LeanUnit |
|---|---|---|
| The claim | The output is correct for the selected inputs. | The law is true for each input. |
| The inputs | You select them. | A failure shows an input that you did not select. |
| The bug above | Not found | Found, with the input that causes it |
| An agent changes the check to make it pass | The tests pass, and nobody sees the change. | `leanunit check` fails until a human approves the changed law. |
| The link to the code | Direct | LeanUnit compares the model with the code on 2,400 random inputs. |

The proof is about the Lean model. Conformance ties the model to your code only on the sampled inputs.

## Requirements

- Lean 4 through [elan](https://github.com/leanprover/elan). The Lean projects pin `leanprover/lean4:v4.36.0`.
- Python 3.11 or later for LeanUnit. LeanUnit has no run-time dependencies.
- An interpreter that can import your code. LeanUnit uses its own interpreter if you do not set one.

LeanUnit runs the Lean sampler with `lean --run`, so it does not need a C compiler.

## Install

LeanUnit is not on PyPI yet. Install it from a clone:

```bash
uv tool install --editable /path/to/leanunit
```

## Quick start

1. Make the files: `leanunit init --source-root src --cover mypackage.module:MyClass`.
2. Write the Lean types and stub mirrors: `leanunit new mypackage.module:MyClass`.
3. Give `LEANUNIT.md` to your agent, or read it yourself. It tells how to complete the models, write draft laws, and prove them.
4. Run `leanunit check` and `leanunit coverage` until only approvals are pending.
5. Read each draft law in `lean/Laws/`, and approve the laws that you agree with: `leanunit approve <law>`.
6. Add `leanunit check` to your build or CI.

To let LeanUnit start an agent for you, set a command in the `[agent]` table of `leanunit.toml`, and run `leanunit fix`.

## Project layout

| Path | Owner | Contents |
|---|---|---|
| `leanunit.toml` | Team | The code to cover, the Lean project, the sample count, and the agent command. |
| `leanunit.lock` | Human | The approved laws. Only `leanunit approve` writes this file. |
| `lean/Laws/` | Human | The laws. An agent can write drafts. |
| `lean/Model/` | Agent | The model functions, each with `@[mirror "module:Qualname"]`. |
| `lean/Gen/` | Agent | The `Sample` instances for the model types. |
| `lean/Proofs/` | Agent | One theorem for each law, or a refutation with `¬`. |
| `LEANUNIT.md` | LeanUnit | The guide for humans and agents. `leanunit guide --write` updates it. |
| `AGENTS.md` | Team | LeanUnit adds one pointer to `LEANUNIT.md`, and adds the same pointer to `CLAUDE.md` if that file exists. |

## Commands

| Command | What it does |
|---|---|
| `leanunit check` | Verifies the laws, the proofs, the conformance, and the coverage. Add `--json` for a report that a program can read. |
| `leanunit coverage` | Shows each covered function, its mirror, its laws, and the lines that the samples executed. |
| `leanunit new <module:Qualname>` | Writes Lean types, `Sample` generators, and a stub mirror for each function, from the Python type hints. |
| `leanunit approve <law>...` | Records the current statement of each law in the lock. Short names are permitted. |
| `leanunit approve --all` | Approves all laws, and removes laws that are gone. |
| `leanunit fix` | Starts the configured agent when the check fails. Then it restores the protected files and checks again. |
| `leanunit guide` | Shows the guide. `leanunit guide --write` writes `LEANUNIT.md` and the pointers. |
| `leanunit init` | Makes `leanunit.toml`, an empty lock, the Lean project, and `LEANUNIT.md`. |

`leanunit check` and `leanunit fix` use these exit codes:

| Code | Meaning |
|---|---|
| 0 | The check passed. |
| 1 | The check found work for an agent or a developer. |
| 2 | The command or the configuration is wrong. |
| 3 | Only a human can clear the findings, for example by an approval. |

## What the check verifies

`leanunit check` passes only when all these conditions are true:

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
For a method, the first argument is the object, and the result is a `LeanUnit.Outcome`:

```lean
@[mirror "strands.interrupt:_InterruptState.activate"]
def activate (s : State) : Outcome State Unit :=
  .ok { s with activated := true, _version := s._version + 1 } ()
```

- `Outcome.ok self ret` is a normal return. `Outcome.raise "KeyError" self` is an exception.
- `LeanUnit.Val` holds any JSON value, for example a field of type `Any`.
- `LeanUnit.Dict α` is a Python `dict[str, T]`.
- The JSON form of each model type must agree with the Python value. Use field names that agree with the Python names.

## Example

`examples/strands-interrupt` covers the `_InterruptState` class of the Strands Agents SDK.
It has 10 laws. LeanUnit proves 9 of them, and it refutes 1 of them.
The refuted law shows a real bug: `resume` can change the state without an increase of the version.
Refer to `examples/strands-interrupt/README.md`.

In `docs/demo.md`, a developer corrects the bug, and the agent updates the model. Then all 14 laws pass.

## Limits

- LeanUnit supports Python only. TypeScript is next, with the same protocol and a new runner.
- LeanUnit supports pure logic only. It does not support I/O, async code, threads, floats, or callbacks.
- LeanUnit mirrors plain functions and the methods of dataclasses. It does not mirror classmethods, staticmethods, properties, or dunder methods.
- Conformance is random testing. A model can differ from the code on inputs that the samples do not include.
- LeanUnit does not shrink a failure. It shows the smallest failure that it found.

Refer to `docs/design.md` for the full design.

## License

LeanUnit has the Apache License 2.0. Refer to `LICENSE`.
The copy of `interrupt.py` in the example also has the Apache License 2.0, with its own `LICENSE` and `NOTICE` files.
