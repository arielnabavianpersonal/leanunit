import NoUnit.Gen
import NoUnit.Outcome

open Lean

namespace NoUnit

structure Mirror where
  target : String
  sample : Nat → Nat → Json × Json

namespace Mirror

variable {α β γ δ ρ : Type}

def of1 [Sample α] [ToJson α] [ToJson ρ] (target : String) (f : α → ρ) : Mirror where
  target := target
  sample size seed :=
    let a : α := Gen.run Sample.sample size seed
    (Json.arr #[toJson a], toJson (f a))

def of2 [Sample α] [Sample β] [ToJson α] [ToJson β] [ToJson ρ]
    (target : String) (f : α → β → ρ) : Mirror where
  target := target
  sample size seed :=
    let draw : Gen (α × β) := do
      let a ← (Sample.sample : Gen α)
      let b ← (Sample.sample : Gen β)
      pure (a, b)
    let (a, b) := Gen.run draw size seed
    (Json.arr #[toJson a, toJson b], toJson (f a b))

def of3 [Sample α] [Sample β] [Sample γ] [ToJson α] [ToJson β] [ToJson γ] [ToJson ρ]
    (target : String) (f : α → β → γ → ρ) : Mirror where
  target := target
  sample size seed :=
    let draw : Gen (α × β × γ) := do
      let a ← (Sample.sample : Gen α)
      let b ← (Sample.sample : Gen β)
      let c ← (Sample.sample : Gen γ)
      pure (a, b, c)
    let (a, b, c) := Gen.run draw size seed
    (Json.arr #[toJson a, toJson b, toJson c], toJson (f a b c))

def of4 [Sample α] [Sample β] [Sample γ] [Sample δ] [ToJson α] [ToJson β] [ToJson γ] [ToJson δ]
    [ToJson ρ] (target : String) (f : α → β → γ → δ → ρ) : Mirror where
  target := target
  sample size seed :=
    let draw : Gen (α × β × γ × δ) := do
      let a ← (Sample.sample : Gen α)
      let b ← (Sample.sample : Gen β)
      let c ← (Sample.sample : Gen γ)
      let d ← (Sample.sample : Gen δ)
      pure (a, b, c, d)
    let (a, b, c, d) := Gen.run draw size seed
    (Json.arr #[toJson a, toJson b, toJson c, toJson d], toJson (f a b c d))

end Mirror

def sampleSeed (seed index : Nat) (target : String) : Nat :=
  (hash target).toNat % 1000003 * 7919 + seed * 104729 + index

def sampleSize (index count maxSize : Nat) : Nat :=
  index * maxSize / max count 1 + 1

def conformMain (mirrors : List Mirror) (args : List String) : IO UInt32 := do
  let count := (args.getD 0 "300").toNat!
  let seed := (args.getD 1 "1").toNat!
  let maxSize := (args.getD 2 "12").toNat!
  let stdout ← IO.getStdout
  for mirror in mirrors do
    for index in [0:count] do
      let (input, expected) :=
        mirror.sample (sampleSize index count maxSize) (sampleSeed seed index mirror.target)
      stdout.putStrLn <| Json.compress <| Json.mkObj
        [("target", Json.str mirror.target), ("args", input), ("expected", expected)]
  return 0

end NoUnit
