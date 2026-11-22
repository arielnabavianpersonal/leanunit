import NoUnit.Val
import NoUnit.Dict

open Lean

namespace NoUnit

abbrev Gen (α : Type) := ReaderT Nat (StateM StdGen) α

class Sample (α : Type) where
  sample : Gen α

namespace Gen

variable {α β : Type}

def size : Gen Nat := read

def resize (n : Nat) (g : Gen α) : Gen α := fun _ => g n

def scale (f : Nat → Nat) (g : Gen α) : Gen α := fun n => g (f n)

def natIn (lo hi : Nat) : Gen Nat := do
  let rng ← get
  let (n, next) := randNat rng lo hi
  set next
  pure n

def nat : Gen Nat := do natIn 0 (← size)

def bool : Gen Bool := do pure ((← natIn 0 1) == 1)

def int : Gen Int := do
  let n ← nat
  let negative ← bool
  pure (if negative then -(n : Int) else n)

def elements (default : α) (xs : List α) : Gen α := do
  if xs.isEmpty then pure default
  else pure (xs.getD (← natIn 0 (xs.length - 1)) default)

def oneOf (default : Gen α) (gs : List (Gen α)) : Gen α := do
  if gs.isEmpty then default
  else (gs.getD (← natIn 0 (gs.length - 1)) default)

def frequency (default : Gen α) (gs : List (Nat × Gen α)) : Gen α := do
  let total := gs.foldl (fun acc (weight, _) => acc + weight) 0
  if total == 0 then default
  else
    let rec pick : Nat → List (Nat × Gen α) → Gen α
      | _, [] => default
      | p, (weight, g) :: rest => if p ≤ weight then g else pick (p - weight) rest
    pick (← natIn 1 total) gs

def listOf (g : Gen α) : Gen (List α) := do
  let n ← nat
  (List.range n).mapM fun _ => g

def optionOf (g : Gen α) : Gen (Option α) := do
  if (← natIn 0 3) == 0 then pure none else some <$> g

def stringChars : List Char := ['a', 'b', 'c', 'x', 'y', 'z', '0', '1', ' ', '-', ':', '_']

def string : Gen String := do
  let n ← natIn 0 (min (← size) 8)
  let chars ← (List.range n).mapM fun _ => elements 'a' stringChars
  pure (String.ofList chars)

def dictOf (g : Gen α) : Gen (Dict α) := do
  let pairs ← listOf (do pure ((← string), (← g)))
  pure (Dict.ofList pairs).sorted

def jsonLeaf : Gen Json :=
  oneOf (pure .null)
    [pure .null, Json.bool <$> bool, (fun n => Json.num ⟨n, 0⟩) <$> int, Json.str <$> string]

def jsonDepth : Nat → Gen Json
  | 0 => jsonLeaf
  | depth + 1 =>
    frequency jsonLeaf
      [(4, jsonLeaf),
       (1, (fun items => Json.arr items.toArray) <$> scale (· / 2) (listOf (jsonDepth depth))),
       (1, (fun (d : Dict Json) => Json.mkObj d.entries) <$> scale (· / 2) (dictOf (jsonDepth depth)))]

def json : Gen Json := do jsonDepth (min (← size) 3)

def run (g : Gen α) (size seed : Nat) : α := ((g size).run (mkStdGen seed)).1

end Gen

instance : Sample Nat := ⟨Gen.nat⟩
instance : Sample Int := ⟨Gen.int⟩
instance : Sample Bool := ⟨Gen.bool⟩
instance : Sample String := ⟨Gen.string⟩
instance : Sample Val := ⟨Val.ofJson <$> Gen.json⟩
instance {α : Type} [Sample α] : Sample (List α) := ⟨Gen.listOf Sample.sample⟩
instance {α : Type} [Sample α] : Sample (Option α) := ⟨Gen.optionOf Sample.sample⟩
instance {α β : Type} [Sample α] [Sample β] : Sample (α × β) :=
  ⟨do pure ((← Sample.sample), (← Sample.sample))⟩
instance {α : Type} [Sample α] : Sample (Dict α) := ⟨Gen.dictOf Sample.sample⟩

end NoUnit
