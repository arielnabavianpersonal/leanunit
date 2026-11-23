import Lean.Data.Json

open Lean

namespace LeanUnit

inductive Outcome (σ ρ : Type) where
  | ok (self : σ) (ret : ρ)
  | raise (exc : String) (self : σ)
deriving DecidableEq, Repr

namespace Outcome

variable {σ ρ : Type}

def self : Outcome σ ρ → σ
  | .ok s _ => s
  | .raise _ s => s

def ret? : Outcome σ ρ → Option ρ
  | .ok _ r => some r
  | .raise _ _ => none

def raised? : Outcome σ ρ → Option String
  | .ok _ _ => none
  | .raise exc _ => some exc

end Outcome

instance : ToJson Unit := ⟨fun _ => .null⟩

instance {σ ρ : Type} [ToJson σ] [ToJson ρ] : ToJson (Outcome σ ρ) where
  toJson
    | .ok s r => Json.mkObj [("self", toJson s), ("return", toJson r)]
    | .raise exc s => Json.mkObj [("raise", Json.str exc), ("self", toJson s)]

end LeanUnit
