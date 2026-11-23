# Agent loop demo

Date: 2026-11-23. The demo used a copy of `examples/strands-interrupt` and `claude -p` as the agent command.
Before the demo, a human approved the 10 laws of the example.

## Run 1: new code adds proofs

1. The developer added the method `answered_ids` to `_InterruptState`.
2. `leanunit check` reported `uncovered_code` for the new method.
3. `leanunit fix` started the agent. The agent added a mirror, three draft laws, and their proofs. It did not edit the code.
4. The draft laws say that `answered_ids` does not change the state, lists only answered interrupts, and lists every answered interrupt.
5. 300 new conformance samples agreed with the Python code.
6. The agent also reported the refuted law as a code bug, and it recommended an atomic `resume`.
7. A human approved the three laws. Only the refuted law stayed.

## Run 2: a change breaks the verification

1. The developer made `resume` atomic, with the intent "I fixed the resume bug on purpose".
2. `leanunit check` reported a `mismatch` for `resume` on 4 samples.
3. `leanunit fix` started the agent. The agent updated the model to the new behavior.
4. The old refutation no longer applied, so the agent deleted it and proved the version law.
5. The agent added the draft law `resume_is_all_or_nothing`, because no law described the new guarantee.
6. The statements of the 13 approved laws did not change, so they needed no new approval.
7. A human approved the new law. `leanunit check` passed with 14 proved laws and 2,700 samples.

## Results

- In the two runs, the guard did not restore a file, because the agent did not change a protected file.
- The agent did not weaken a law in the two runs.
