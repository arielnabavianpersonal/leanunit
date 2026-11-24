# LeanUnit design

Status: approved in chat on 2026-11-22. This document describes version 1.

## Purpose

LeanUnit replaces hand-written unit tests for pure logic with Lean proofs.
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
| `Laws/` | Human | The agent can write a draft law. Only `leanunit approve` makes the law valid. |
| `Model/`, `Proofs/`, `Gen/` | Agent | The agent can change these files. Lean and conformance verify them. |
| `leanunit.lock` | Human | Only `leanunit approve` writes this file. |
| `leanunit.toml` and the code | Team | `leanunit fix` cannot change them. |

## The lock file

`leanunit.lock` is JSON, like `package-lock.json`.
It records the Lean toolchain, one entry for each approved law, and one entry for each approved exclusion.

```json
{
  "lockfileVersion": 2,
  "leanToolchain": "leanprover/lean4:v4.36.0",
  "laws": {
    "Laws.Interrupt.no_standing_approval": {
      "statement": "sha256:9f2c...",
      "covers": ["strands.interrupt:_InterruptState.to_dict"],
      "approvedBy": "dev@example.com",
      "approvedAt": "2026-11-22"
    }
  },
  "exclusions": {
    "strands.interrupt:_InterruptState.from_dict": {
      "approvedBy": "dev@example.com",
      "approvedAt": "2026-11-24"
    }
  }
}
```

## The statement hash

The hash covers all the parts that give a law its meaning.
LeanUnit follows each constant that the law uses.
It stops at mirrored functions, because conformance ties them to the code.
It also stops at constants from Lean, Std, and LeanUnit.

The hash includes the type and the value of all other constants.
Thus, a change to a helper that a law uses changes the hash of the law.
The mirror targets that the law uses are also part of the hash.

## Commands

### `leanunit init`

This command makes the Lean project, `leanunit.toml`, and an empty lock.

### `leanunit check`

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

### `leanunit approve`

`leanunit approve <law>...` or `leanunit approve --all` writes the current hashes into the lock.
It records the git user as the approver.
It stops with an error when the environment variable `LEANUNIT_AGENT` is set.

### `leanunit fix`

1. It runs the check. If the check passes, the command stops.
2. It starts the agent command from `leanunit.toml`. On stdin, it sends the report, the uncommitted diff of the code, and the `--intent` text.
3. It restores each protected file that the agent changed.
4. It runs the check again and shows the result and the diagnosis of the agent.

The agent puts each failure into one of these classes:

- A proof fails, but the behavior did not change: the agent repairs the proof.
- Conformance fails: the agent reports a code bug, or it updates the model for an intended change.
- A law has a refutation: the agent reports the counterexample.
- Code has no law: the agent writes a model, generators, draft laws, and proofs.

## Version 0.2: one platform for each kind of user

LeanUnit works like a unit test framework. A human, a personal agent, a workspace agent, or a CI job uses the same commands.
The repository owner can automate the repair with `leanunit fix`. One designated agent is not necessary.
LeanUnit has no flags that are specific to one CI service or one code host.

### `leanunit coverage`

This command runs the same steps as `leanunit check`.
For each target, it shows the mirror, the laws that use the mirror, and the lines that the samples executed.

### `leanunit new`

This command reads the types of a target. For Python, the runner reads the type hints. For TypeScript and JavaScript, `node_describe.mjs` reads the types.
It writes Lean structures for the dataclasses, `Sample` instances for these structures, and one stub mirror for each function.
Each stub raises `NotImplementedError`, so the first check shows the real output of each function as a `mismatch`.
The command skips functions in the `exclude` list, dunder methods, and functions that the class source does not contain.

### `leanunit guide`

This command shows the guide for humans and agents. `leanunit guide --write` writes the guide to `LEANUNIT.md`.
It also adds a pointer to `LEANUNIT.md` in `AGENTS.md`, and in `CLAUDE.md` if that file exists.
`leanunit init` writes these files too. The prompt of `leanunit fix` starts with the same guide.

### Exit codes

`leanunit check` and `leanunit fix` exit with 0 when the check passes, and with 1 when work remains for an agent or a developer.
They exit with 3 when only a human can clear the findings, for example an approval. A usage or configuration error gives 2.

## Conformance protocol

The Lean sampler writes one JSON line for each sample, with `target`, `args`, and `expected`.
The runner reads `target` and `args`, calls the function, and writes the outcome.
After the last sample, the runner writes the line coverage.
LeanUnit compares the expected outcome and the actual outcome as JSON, with object keys in any order and numbers by value.

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
- Version 1 does not shrink a failure. The sample size starts small and increases, and LeanUnit shows the smallest failure.
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

## Tests for LeanUnit

Pytest tests cover the Python core: the lock, the codec, the runner, line coverage, the check report, `approve`, and the file guard in `fix`.
An integration test runs `leanunit check` on the example when `lake` is available.

## Version 0.4: more languages

The `languages` module hides each difference between languages behind one interface.
The interface gives the runner command, the type description, and the methods of a class.
It also finds the source file of a module and the source files to protect.
The table name in `leanunit.toml` selects the language. The default is Python.

TypeScript and JavaScript share one runner, `node_runner.mjs`. It uses the same JSON protocol as the Python runner.
The runner makes an object of the class from the JSON fields, and it waits for the result of an async function.
It measures line coverage with the precise coverage of V8. Type stripping keeps the source positions, so the line numbers agree with the TypeScript file.

The helper `node_describe.mjs` reads the types through the TypeScript compiler API of the project.
It gives the same type tree as the Python runner, so `leanunit new` writes Lean in the same way for each language.
A new language needs a runner and a describe helper. The Lean library and the core do not change.

## Version 0.5: more of the Python code

A benchmark on the Strands Agents SDK found these causes for the bugs that LeanUnit missed:

| Cause | Misses |
|---|---|
| The bug was in code that version 0.3 cannot mirror. | 117 |
| The bug needed an input that JSON cannot carry. | 39 |
| The bug changed a default value. | 12 |

Version 0.5 removes most of these causes.

- The Python runner mirrors properties, classmethods, staticmethods, constructors, and value methods such as `__str__`.
- A parameter with a default value has the Lean type `Arg α`. The value `.default` makes the runner leave out the argument.
- The runners send `bytes`, special floats, enums, sets, plain objects, and functions as tagged JSON objects.
- The lock records each approved exclusion. An unapproved exclusion gives the human-owned finding `unapproved_exclusion`.
- A private method of a covered class is a helper. A helper needs no mirror, but the samples must execute each of its lines.
  Thus, a refactor that extracts a private method does not make the check fail.

The lock file has version 2. LeanUnit reads a version 1 lock as a lock without exclusions.
