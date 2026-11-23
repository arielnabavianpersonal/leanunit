import LeanUnit.Val

open Lean

namespace LeanUnit

structure Dict (α : Type) where
  entries : List (String × α)
deriving DecidableEq, Inhabited, Repr

namespace Dict

variable {α : Type}

def empty : Dict α := ⟨[]⟩

def get? (d : Dict α) (key : String) : Option α := d.entries.lookup key

def keys (d : Dict α) : List String := d.entries.map Prod.fst

def values (d : Dict α) : List α := d.entries.map Prod.snd

def contains (d : Dict α) (key : String) : Bool := d.entries.any (·.1 == key)

def insert (d : Dict α) (key : String) (value : α) : Dict α :=
  if d.contains key then
    ⟨d.entries.map fun (k, v) => if k == key then (k, value) else (k, v)⟩
  else
    ⟨d.entries ++ [(key, value)]⟩

def filter (d : Dict α) (keep : String → α → Bool) : Dict α :=
  ⟨d.entries.filter fun (k, v) => keep k v⟩

def ofList (pairs : List (String × α)) : Dict α :=
  pairs.foldl (fun d (k, v) => d.insert k v) empty

def sorted (d : Dict α) : Dict α :=
  ⟨d.entries.mergeSort fun a b => a.1 < b.1 || a.1 == b.1⟩

theorem mem_keys_filter {d : Dict α} {keep : String → α → Bool} {key : String}
    (h : key ∈ (d.filter keep).keys) : ∃ value, keep key value = true := by
  simp only [keys, filter, List.mem_map, List.mem_filter] at h
  obtain ⟨⟨k, v⟩, ⟨_, hkeep⟩, rfl⟩ := h
  exact ⟨v, hkeep⟩

theorem lookup_filter {keep : String → α → Bool} {key : String} {value : α} :
    ∀ (entries : List (String × α)),
      (entries.filter fun (k, v) => keep k v).lookup key = some value → keep key value = true := by
  intro entries
  induction entries with
  | nil => simp
  | cons head tail ih =>
    obtain ⟨k, v⟩ := head
    intro h
    by_cases hk : keep k v = true
    · rw [List.filter_cons_of_pos (by simpa using hk)] at h
      by_cases heq : key = k
      · subst heq
        simp only [List.lookup, beq_self_eq_true, Option.some.injEq] at h
        subst h
        exact hk
      · have hne : (key == k) = false := by simpa using heq
        simp only [List.lookup, hne] at h
        exact ih h
    · rw [List.filter_cons_of_neg (by simpa using hk)] at h
      exact ih h

theorem get?_filter {d : Dict α} {keep : String → α → Bool} {key : String} {value : α}
    (h : (d.filter keep).get? key = some value) : keep key value = true :=
  lookup_filter d.entries h

private theorem lookup_cons_eq_ite {k k' : String} {v : α} {rest : List (String × α)} :
    ((k', v) :: rest).lookup k = if k = k' then some v else rest.lookup k := by
  by_cases h : k = k'
  · subst h
    simp
  · simp [List.lookup_cons, beq_false_of_ne h, h]

private theorem lookup_map_replace {key k : String} {value : α} :
    ∀ entries : List (String × α),
      (entries.map fun (k', v) => if k' == key then (k', value) else (k', v)).lookup k =
        if k = key then (entries.lookup k).map fun _ => value else entries.lookup k
  | [] => by simp
  | (k', v) :: rest => by
    have ih := lookup_map_replace (key := key) (k := k) (value := value) rest
    by_cases hk' : k' = key <;> by_cases hk : k = k' <;> by_cases hkey : k = key <;>
      simp_all [lookup_cons_eq_ite]

theorem get?_insert {d : Dict α} {key k : String} {value : α} :
    (d.insert key value).get? k = if k = key then some value else d.get? k := by
  obtain ⟨entries⟩ := d
  unfold insert get? contains
  by_cases hcontains : entries.any (·.1 == key) = true
  · simp only [hcontains, ↓reduceIte, lookup_map_replace]
    by_cases hk : k = key
    · subst hk
      cases hfound : entries.lookup k with
      | none =>
        obtain ⟨p, hp, hpk⟩ := List.any_eq_true.mp hcontains
        have hmiss := List.lookup_eq_none_iff.mp hfound p hp
        simp_all
      | some found => simp
    · simp [hk]
  · simp only [hcontains, Bool.false_eq_true, ↓reduceIte, List.lookup_append, lookup_cons_eq_ite,
      List.lookup_nil]
    by_cases hk : k = key
    · subst hk
      have hnone : entries.lookup k = none := by
        refine List.lookup_eq_none_iff.mpr fun p hp => ?_
        have hother : p.1 ≠ k := fun hpk => hcontains (List.any_eq_true.mpr ⟨p, hp, by simp [hpk]⟩)
        simpa using hother.symm
      simp [hnone]
    · simp [hk, Option.or_none]

end Dict

instance {α : Type} [ToJson α] : ToJson (Dict α) :=
  ⟨fun d => Json.mkObj (d.entries.map fun (key, value) => (key, toJson value))⟩

instance {α : Type} [FromJson α] : FromJson (Dict α) :=
  ⟨fun json => do
    let kvs ← json.getObj?
    let pairs := kvs.foldl (fun acc key value => acc.push (key, value)) (#[] : Array (String × Json))
    return ⟨← pairs.toList.mapM fun (key, value) => return (key, ← fromJson? value)⟩⟩

end LeanUnit
