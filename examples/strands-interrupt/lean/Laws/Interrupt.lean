import Model.Interrupt

open NoUnit Model.Interrupt

namespace Laws.Interrupt

@[law] def no_standing_approval : Prop :=
  ∀ s snapshot, s.activated = false → (to_dict s).ret? = some snapshot →
    ∀ id ∈ snapshot.interrupts.keys, isStream id = false

@[law] def deactivate_clears : Prop :=
  ∀ s, (deactivate s).self.interrupts = Dict.empty ∧ (deactivate s).self.context = Dict.empty ∧
    (deactivate s).self.activated = false ∧ (deactivate s).self.pending_tool_execution = none

@[law] def resume_inactive_is_noop : Prop :=
  ∀ s prompt, s.activated = false → resume s prompt = .ok s ()

@[law] def resume_stores_no_null : Prop :=
  ∀ s prompt s', resume s prompt = .ok s' () →
    ∀ id interrupt, s'.interrupts.get? id = some interrupt → s.interrupts.get? id ≠ some interrupt →
      interrupt.response ≠ Val.null

@[law] def resume_bumps_version_on_change : Prop :=
  ∀ s prompt, (resume s prompt).self ≠ s → (resume s prompt).self._version > s._version

@[law] def activate_sets_flag : Prop :=
  ∀ s, (activate s).self.activated = true

@[law] def end_tool_cycle_keeps_answered_stream_interrupts : Prop :=
  ∀ s id interrupt, (end_tool_cycle s).self.interrupts.get? id = some interrupt →
    isStream id = true ∧ interrupt.response ≠ Val.null

@[law] def end_interrupt_cycle_drops_stream_interrupts : Prop :=
  ∀ s, ∀ id ∈ (end_interrupt_cycle s).self.interrupts.keys, isStream id = false

@[law] def set_pending_tool_results_needs_pending : Prop :=
  ∀ s results, s.pending_tool_execution = none → set_pending_tool_results s results = .ok s ()

@[law] def get_version_reads_the_version : Prop :=
  ∀ s, _get_version s = .ok s s._version

end Laws.Interrupt
