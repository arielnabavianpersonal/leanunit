import LeanUnit.Gen

open Lean

namespace LeanUnit

inductive Arg (α : Type) where
  | given (value : α)
  | default
deriving DecidableEq, Repr

namespace Arg

variable {α : Type}

def getD : Arg α → α → α
  | .given value, _ => value
  | .default, fallback => fallback

def defaultMark : Json := Json.mkObj [("__default__", Json.bool true)]

end Arg

instance {α : Type} [ToJson α] : ToJson (Arg α) where
  toJson
    | .given value => toJson value
    | .default => Arg.defaultMark

instance {α : Type} [FromJson α] : FromJson (Arg α) where
  fromJson? json := if json == Arg.defaultMark then .ok .default else Arg.given <$> fromJson? json

instance {α : Type} [Sample α] : Sample (Arg α) :=
  ⟨do if (← Gen.natIn 0 3) == 0 then pure .default else Arg.given <$> Sample.sample⟩

end LeanUnit
