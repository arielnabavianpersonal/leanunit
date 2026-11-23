import Model.Mini

open LeanUnit Model.Mini

namespace Laws.Mini

@[law] def inc_positive : Prop := ∀ n r, (inc n).ret? = some r → helper r

@[law] def inc_big : Prop := ∀ n r, (inc n).ret? = some r → r > 5

@[law] def inc_nonzero : Prop := ∀ n r, (inc n).ret? = some r → r ≠ 0

@[law] def inc_at_least_one : Prop := ∀ n r, (inc n).ret? = some r → r ≥ 1

@[law] def double_even : Prop := ∀ n, double n % 2 = 0

@[law] def unproved : Prop := ∀ n : Nat, n + 0 = n

end Laws.Mini
