# Example: the Strands interrupt state

This example covers the `_InterruptState` class of the Strands Agents SDK.
The file `src/strands/interrupt.py` is a copy from `strands-agents/harness-sdk` at commit `d6c5fae7`, with no changes.
The Strands Agents SDK has the Apache 2.0 license.

## What LeanUnit verifies

The model in `lean/Model/Interrupt.lean` mirrors 8 methods. Version 1 does not cover `from_dict`.
On each check, LeanUnit compares the model and the real code on 2,400 random samples.
The samples execute each line of the 8 methods.

## The laws

| Law | Meaning | Result |
|---|---|---|
| `no_standing_approval` | When the state is inactive, `to_dict` writes no invocation-scoped interrupt. | Proved |
| `deactivate_clears` | `deactivate` clears the interrupts, the context, and the pending tool execution. | Proved |
| `resume_inactive_is_noop` | `resume` does nothing when the state is inactive. | Proved |
| `resume_stores_no_null` | Each interrupt that a successful `resume` changes has a response that is not `null`. | Proved |
| `resume_bumps_version_on_change` | When `resume` changes the state, the version increases. | **Refuted** |
| `activate_sets_flag` | `activate` makes the state active. | Proved |
| `end_tool_cycle_keeps_answered_stream_interrupts` | After `end_tool_cycle`, each interrupt is invocation-scoped and has a response. | Proved |
| `end_interrupt_cycle_drops_stream_interrupts` | After `end_interrupt_cycle`, no interrupt is invocation-scoped. | Proved |
| `set_pending_tool_results_needs_pending` | `set_pending_tool_results` does nothing when no tool execution is pending. | Proved |
| `get_version_reads_the_version` | `_get_version` returns the version and changes nothing. | Proved |

## The bug that the refuted law shows

The docstring of `_get_version` says that each change to the state increments the version.
But `resume` can change the state without an increase of the version.
When one response in a prompt has an unknown interrupt ID, `resume` raises `KeyError`.
Before it raises, it already stored the earlier responses.
It does not increment the version, so a consumer that compares versions does not see the change.

This Python code shows the bug on the real class:

```python
from strands.interrupt import Interrupt, _InterruptState

state = _InterruptState()
state.interrupts["a"] = Interrupt("a", "approve")
state.activate()
version = state._get_version()
try:
    state.resume([
        {"interruptResponse": {"interruptId": "a", "response": "yes"}},
        {"interruptResponse": {"interruptId": "missing", "response": "x"}},
    ])
except KeyError:
    pass
assert state.interrupts["a"].response == "yes"
assert state._get_version() == version
```

The Lean refutation is `resume_bumps_version_on_change_refuted` in `lean/Proofs/Interrupt.lean`. The Lean kernel verifies it.

## Run the example

1. Install LeanUnit and elan. Refer to the README at the root of the repository.
2. Run `leanunit --root examples/strands-interrupt check`. All 10 laws show as not approved.
3. Read the laws in `lean/Laws/Interrupt.lean`.
4. Run `leanunit --root examples/strands-interrupt approve --all`.
5. Run the check again. Only the refuted law stays.

To clear the last finding, a human must decide: correct `resume`, or change the law.
