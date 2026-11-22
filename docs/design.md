# NoUnit design

Status: approved in chat on 2026-11-22. This document describes version 1.

## Purpose

NoUnit replaces hand-written unit tests for pure logic with Lean proofs.
A lock file records the laws that a human approved.
The build fails when a change breaks a law.
An agent repairs the proofs and writes drafts of new laws.
A human approves each new or changed law.

## Terms

| Term | Meaning |
|---|---|
| Law | A Lean statement that the code must obey. A human approves it. |
| Proof | A Lean proof of a law. An agent writes it, and the Lean kernel verifies it. |
| Refutation | A Lean proof that a law is false. |
| Model | A copy of the code logic in Lean. |
| Mirror | A link from a model function to a code function. |
| Conformance | A comparison of a model function and its code function on the same random inputs. |
| Runner | A small program in the language of the code. It reads JSON inputs, calls the function, and writes JSON outputs. |

## Who changes what

| Path | Owner | Rule |
|---|---|---|
| `Laws/` | Human | The agent can write a draft law. Only `nounit approve` makes the law valid. |
| `Model/`, `Proofs/`, `Gen/` | Agent | The agent can change these files. Lean and conformance verify them. |
| `nounit.lock` | Human | Only `nounit approve` writes this file. |
| `nounit.toml` and the code | Team | `nounit fix` cannot change them. |

## The lock file

`nounit.lock` is JSON, like `package-lock.json`.
It records the Lean toolchain and one entry for each approved law.

```json
{
  "lockfileVersion": 1,
  "leanToolchain": "leanprover/lean4:v4.36.0",
  "laws": {
    "Laws.Interrupt.no_standing_approval": {
      "statement": "sha256:9f2c...",
      "covers": ["strands.interrupt:_InterruptState.to_dict"],
      "approvedBy": "arielnab@amazon.com",
      "approvedAt": "2026-11-22"
    }
  }
}
```

## The statement hash

The hash covers all the parts that give a law its meaning.
NoUnit follows each constant that the law uses.
It stops at mirrored functions, because conformance ties them to the code.
It also stops at constants from Lean, Std, and NoUnit.

The hash includes the type and the value of all other constants.
Thus, a change to a helper that a law uses changes the hash of the law.
The mirror targets that the law uses are also part of the hash.

## Commands

### `nounit init`

This command makes the Lean project, `nounit.toml`, and an empty lock.

### `nounit check`

This command is the build step. It does these steps:

1. It builds the Lean project.
2. It runs the audit. The audit finds each law, its proof or refutation, the axioms of the proof, and the hash.
3. It compares the hashes with the lock.
4. It runs conformance for each mirror, and it measures the line coverage of each code function.
5. It finds code in the `cover` list that has no mirror, and mirrors that no law uses.

The command passes only when all these conditions are true:

- Each law is approved, and its hash agrees with the lock.
- Each law has a proof, and no law has a refutation.
- No proof uses `sorry` or an axiom other than `propext`, `Classical.choice`, and `Quot.sound`.
- No project constant has `@[implemented_by]` or `@[extern]`.
- Each mirror agrees with its code function on all samples.
- The samples execute each line of each mirrored code function.
- Each function in the `cover` list has a mirror, and a law uses each mirror.

### `nounit approve`

`nounit approve <law>...` or `nounit approve --all` writes the current hashes into the lock.
It records the git user as the approver.
It stops with an error when the environment variable `NOUNIT_AGENT` is set.

### `nounit fix`

1. It runs the check. If the check passes, the command stops.
2. It starts the agent command from `nounit.toml`, and it sends the report on stdin.
3. It restores each protected file that the agent changed.
4. It runs the check again and shows the result and the diagnosis of the agent.

The agent puts each failure into one of these classes:

- A proof fails, but the behavior did not change: the agent repairs the proof.
- Conformance fails: the agent reports a code bug, or it updates the model for an intended change.
- A law has a refutation: the agent reports the counterexample.
- Code has no law: the agent writes a model, generators, draft laws, and proofs.

## Conformance protocol

The Lean sampler writes one JSON line for each sample, with `target`, `args`, and `expected`.
The runner reads `target` and `args`, calls the function, and writes the outcome.
After the last sample, the runner writes the line coverage.
NoUnit compares the expected outcome and the actual outcome as JSON, with object keys in any order.

An outcome has one of these two forms:

- `{"self": <state after the call>, "return": <value>}`
- `{"raise": "<exception class name>", "self": <state after the call>}`

For a method, the first argument is the object, and `self` is the object after the call.
For a function, `self` is `null`.

The Python runner converts JSON to Python values from the type hints:

- A dataclass is an object with one key for each field.
- A `dict[str, T]` is an object.
- A `list[T]` is an array.
- `T | None` is `null` or a `T`.
- `Any` and a `TypedDict` stay as plain JSON.

## Limits of version 1

- Version 1 supports Python only. TypeScript is next, with the same protocol and a new runner.
- Version 1 supports pure logic only. It does not support I/O, async code, threads, floats, or callbacks.
- Version 1 does not shrink a failure. The sample size starts small and increases, and NoUnit shows the smallest failure.
- Conformance is random testing. A model can differ from the code on inputs that the samples do not include. The line coverage rule decreases this risk.

## First target

The first target is `_InterruptState` in `strands-py/src/strands/interrupt.py`, from harness-sdk commit `d6c5fae7`.
The example in `examples/strands-interrupt` contains a copy of this file.
Version 1 does not cover `from_dict`, because it imports other modules of the package.
The first laws are:

- When the state is inactive, `to_dict` writes no invocation-scoped interrupt.
- `deactivate` clears the interrupts, the context, and the pending tool execution.
- `resume` does nothing when the state is inactive.
- A successful `resume` stores no `null` response.
- Each change to the state increments the version. This law is false for the current code.

## Tests for NoUnit

Pytest tests cover the Python core: the lock, the codec, the runner, line coverage, the check report, `approve`, and the file guard in `fix`.
An integration test runs `nounit check` on the example when `lake` is available.
