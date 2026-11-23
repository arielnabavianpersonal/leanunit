import Laws.Interrupt

open LeanUnit Model.Interrupt

namespace Proofs.Interrupt

theorem no_standing_approval_holds : Laws.Interrupt.no_standing_approval := by
  intro s shown hinactive hshown id hid
  simp only [to_dict, Outcome.ret?, Option.some.injEq] at hshown
  subst hshown
  simp only [snapshot, hinactive, Bool.false_eq_true, ↓reduceIte] at hid
  obtain ⟨_, hkeep⟩ := Dict.mem_keys_filter hid
  simpa [notStream] using hkeep

theorem deactivate_clears_holds : Laws.Interrupt.deactivate_clears :=
  fun _ => ⟨rfl, rfl, rfl, rfl⟩

theorem resume_inactive_is_noop_holds : Laws.Interrupt.resume_inactive_is_noop := by
  intro s prompt hinactive
  simp [resume, hinactive]

theorem applyResponses_stores_no_null :
    ∀ (items : List Block) (before after : Dict Interrupt), applyResponses before items = .ok after →
      ∀ id interrupt, after.get? id = some interrupt → before.get? id ≠ some interrupt →
        interrupt.response ≠ Val.null
  | [], before, after, happlied => by
    simp only [applyResponses, Except.ok.injEq] at happlied
    subst happlied
    exact fun _ _ hafter hbefore => absurd hafter hbefore
  | .text _ :: rest, before, after, happlied => applyResponses_stores_no_null rest before after happlied
  | .response answered answer :: rest, before, after, happlied => by
    simp only [applyResponses] at happlied
    split at happlied
    · contradiction
    rename_i original _
    split at happlied
    · contradiction
    rename_i hanswer
    intro id stored hafter hbefore
    by_cases hthisStep : (before.insert answered { original with response := answer }).get? id = some stored
    · rw [Dict.get?_insert] at hthisStep
      split at hthisStep
      · cases hthisStep
        exact fun hnull => hanswer (Val.isNull_iff.mpr hnull)
      · exact absurd hthisStep hbefore
    · exact applyResponses_stores_no_null rest _ after happlied id stored hafter hthisStep

theorem resume_stores_no_null_holds : Laws.Interrupt.resume_stores_no_null := by
  intro s prompt s' hresumed id interrupt hafter hbefore
  unfold resume at hresumed
  split at hresumed
  · cases hresumed
    exact absurd hafter hbefore
  split at hresumed
  · cases hresumed
  split at hresumed
  · cases hresumed
  split at hresumed
  · cases hresumed
  rename_i updated happlied
  cases hresumed
  exact applyResponses_stores_no_null _ _ _ happlied id interrupt hafter hbefore

def oneUnansweredInterrupt : State :=
  { interrupts := ⟨[("a", { id := "a", name := "approve", reason := Val.null, response := Val.null })]⟩
    context := Dict.empty
    activated := true
    pending_tool_execution := none
    _version := 0 }

def answerThenUnknownId : Prompt :=
  .blocks [.response "a" { json := "\"yes\"" }, .response "missing" { json := "\"x\"" }]

theorem resume_bumps_version_on_change_refuted : ¬ Laws.Interrupt.resume_bumps_version_on_change := by
  intro law
  have changed : (resume oneUnansweredInterrupt answerThenUnknownId).self ≠ oneUnansweredInterrupt := by
    decide
  have sameVersion :
      (resume oneUnansweredInterrupt answerThenUnknownId).self._version = oneUnansweredInterrupt._version := by
    decide
  have bumped := law oneUnansweredInterrupt answerThenUnknownId changed
  omega

theorem activate_sets_flag_holds : Laws.Interrupt.activate_sets_flag :=
  fun _ => rfl

theorem end_tool_cycle_keeps_answered_stream_interrupts_holds :
    Laws.Interrupt.end_tool_cycle_keeps_answered_stream_interrupts := by
  intro s id interrupt hkept
  have hkeep := Dict.get?_filter hkept
  simp only [keepAfterToolCycle, Bool.and_eq_true, Bool.not_eq_true'] at hkeep
  exact ⟨hkeep.1, fun hnull => by simp [Val.isNull_iff.mpr hnull] at hkeep⟩

theorem end_interrupt_cycle_drops_stream_interrupts_holds :
    Laws.Interrupt.end_interrupt_cycle_drops_stream_interrupts := by
  intro s id hid
  unfold end_interrupt_cycle at hid
  split at hid
  · rename_i hnoStream
    simpa using List.all_eq_true.mp hnoStream id hid
  · obtain ⟨_, hkeep⟩ := Dict.mem_keys_filter hid
    simpa [notStream] using hkeep

theorem set_pending_tool_results_needs_pending_holds :
    Laws.Interrupt.set_pending_tool_results_needs_pending := by
  intro s results hnone
  simp [set_pending_tool_results, hnone]

theorem get_version_reads_the_version_holds : Laws.Interrupt.get_version_reads_the_version :=
  fun _ => rfl

end Proofs.Interrupt
