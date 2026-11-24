# LeanUnit guide

LeanUnit replaces hand-written unit tests with Lean proofs. A human, a personal agent, a workspace agent, or a CI job can use the same commands.
A human approves each law. Anyone can write the models, the generators, and the proofs, because Lean and conformance verify them.

## Commands

| Command | What it does |
|---|---|
| `leanunit check` | Verifies the laws, the proofs, the conformance, and the coverage. Add `--json` for a report that a program can read. |
| `leanunit coverage` | Shows each covered function, its mirror, its laws, and the lines that the samples executed. |
| `leanunit new module:Qualname` | Writes the Lean types, the generators, and a stub mirror for each function. |
| `leanunit fix` | Starts the agent that `leanunit.toml` names, sends it the report, and checks again. |
| `leanunit approve <law>` | Records that a human approved a law. |
| `leanunit guide` | Shows this guide. `leanunit guide --write` writes it to `LEANUNIT.md`. |

## Exit codes

| Code | Meaning | Next step |
|---|---|---|
| 0 | The check passed. | Continue. |
| 1 | The check found work for an agent or a developer. | Do the step for each finding. |
| 2 | The command or the configuration is wrong. | Read the error message. |
| 3 | Only a human can clear the findings. | Tell a human which laws to approve. |

## Files

| Path | Who changes it |
|---|---|
| `leanunit.toml` | The team. It names the code to cover. |
| `leanunit.lock` | Only `leanunit approve`. Do not edit it. |
| `lean/Laws/` | Anyone can write a draft law. A draft law has no effect until a human approves it. |
| `lean/Model/`, `lean/Gen/`, `lean/Proofs/` | Anyone. Lean and conformance verify these files. |

## After you change covered code

1. Run `leanunit check`.
2. For each finding, do the step in the table below.
3. Run `leanunit check` again. Stop when the exit code is 0 or 3.
4. If the exit code is 3, tell a human which laws need approval.

| Finding | What to do |
|---|---|
| `mismatch` | Compare the model and the code on the counterexample. If your change is wrong, correct the code. If your change is on purpose, update the model. |
| `refuted_law` | The code or the law is wrong. Correct the code, or ask a human to change the law. |
| `open_law` | Write a theorem whose type is exactly the law. |
| `bad_axiom` | Remove `sorry` or the extra axiom from the proof. |
| `forbidden_constant` | Write the definition again without the forbidden feature. |
| `missing_lines` | Change the generators in `lean/Gen/`, so that the samples execute the missing lines. |
| `uncovered_code` | Run `leanunit new` for the code, then complete the model. |
| `unused_mirror` | Write a draft law that uses the mirror, and prove it. |
| `harness_error` | Correct the model types, so that their JSON form agrees with the types in the code. |
| `lean_error` | Correct the Lean error in the log. |
| `unapproved_law`, `changed_law`, `removed_law`, `toolchain_changed`, `target_error` | A human must do this step. |

## Add laws for new code

1. Run `leanunit new module:Qualname`. It writes the types, the generators, and a stub for each function.
2. Add the target to the `cover` list in `leanunit.toml`, if it is not there.
3. Run `leanunit check`. Each stub raises `NotImplementedError`, so each `mismatch` shows the real output of the code.
4. Write each model function to give the real output. Run `leanunit check` until no `mismatch` stays.
5. Write a draft law in `lean/Laws/` for each behavior that the code must keep.
6. Prove each law in `lean/Proofs/`, or prove that it is false with `¬`.
7. Run `leanunit coverage` to find the functions that have no laws.
8. Ask a human to approve the draft laws.

## Targets in each language

The table name in `leanunit.toml` is the language of the code: `[python]`, `[typescript]`, or `[javascript]`.

| Language | Target examples |
|---|---|
| Python | `strands.interrupt:_InterruptState` and `strands.interrupt:_InterruptState.resume` |
| TypeScript or JavaScript | `src/interrupt:InterruptState` and `src/interrupt:InterruptState.resume` |

For TypeScript and JavaScript, the module is the path from `source_root`, without the file extension.
A TypeScript `number` becomes a Lean `Int`. A field or a parameter without a type becomes `Val`.

## Rules

- Do not edit `leanunit.lock`. Do not run `leanunit approve`, unless you are the human who approves.
- Do not change a law to make a proof easier. If a law is false, prove that it is false.
- Do not use `sorry`, `native_decide`, `axiom`, `implemented_by`, `extern`, `unsafe`, or `partial`.
- A proof is a theorem whose type is exactly the law. A refutation has the type `¬` and the law.
- A model function has `@[mirror "module:Qualname"]` and returns `LeanUnit.Outcome`.
- `Outcome.ok self ret` is a normal return. `Outcome.raise "KeyError" self` is an exception.
