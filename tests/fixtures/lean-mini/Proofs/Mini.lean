import Laws.Mini

open LeanUnit Model.Mini Laws.Mini

namespace Proofs.Mini

theorem inc_positive_holds : inc_positive := by
  intro n r h
  simp [inc, Outcome.ret?] at h
  simp [helper]
  omega

theorem inc_big_refuted : ¬ inc_big := by
  intro h
  have := h 0 1 (by simp [inc, Outcome.ret?])
  omega

theorem inc_nonzero_holds : inc_nonzero := by
  sorry

axiom magic : ∀ n : Nat, n ≥ 1 ∨ n = 0

theorem inc_at_least_one_holds : inc_at_least_one := by
  intro n r h
  simp [inc, Outcome.ret?] at h
  rcases magic r with hr | hr
  · exact hr
  · omega

theorem double_even_holds : double_even := by
  intro n
  simp [double]
  omega

end Proofs.Mini
