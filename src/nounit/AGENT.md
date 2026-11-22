# NoUnit agent guide

You repair a NoUnit project after `nounit check` fails.
NoUnit replaces unit tests with Lean proofs. A human approves each law. You write the proofs, the models, and the generators.

## Rules

- Do not edit the code under test, `nounit.toml`, `nounit.lock`, the lakefile, or `lean-toolchain`. NoUnit restores these files after you stop.
- Do not run `nounit approve`. Only a human approves a law.
- Do not use `sorry`, `native_decide`, `axiom`, `implemented_by`, `extern`, `unsafe`, or `partial`.
- You can edit the files in `Model/`, `Proofs/`, and `Gen/`.
- You can add a draft law to `Laws/`. A draft law has no effect until a human approves it.
- Do not change a law to make a proof easier. If a law is false, prove that it is false.
- Write a proof as a theorem whose type is exactly the law, or `¬` and the law for a refutation.

## What to do for each finding

| Finding | What to do |
|---|---|
| `open_law` | Write a theorem whose type is exactly the law. |
| `bad_axiom` | Remove `sorry` or the extra axiom from the proof. |
| `forbidden_constant` | Write the definition again without the forbidden feature. |
| `mismatch` | Compare the model and the code on the counterexample. Then do one of the two steps below. |
| `missing_lines` | Change the generators in `Gen/`, so that the samples execute the missing lines. |
| `uncovered_code` | Add a model function with `@[mirror "module:Qualname"]`, generators for its inputs, a draft law, and a proof. |
| `unused_mirror` | Add a draft law that uses the mirror, and prove it. |
| `refuted_law` | Do not change the law. Report the counterexample. Tell the human if the code or the law is wrong. |
| `lean_error` | Correct the Lean error in a file that you can edit. |
| `harness_error` | Correct the model types, so that their JSON form agrees with the Python types. |
| `unapproved_law`, `changed_law`, `removed_law`, `toolchain_changed`, `target_error` | Do nothing. These findings are for a human. |

For a `mismatch`, do one of these two steps:

1. If the code changed on purpose, update the model, and prove the laws again.
2. If the code is wrong, do not change the model. Report the bug and the counterexample.

## Before you stop

1. Run the check command again.
2. Write the diagnosis file. For each finding, write one line: the finding, what you did, and what a human must decide.
