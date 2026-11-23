import Lean.Data.Json

open Lean

namespace LeanUnit

structure Val where
  json : String
deriving DecidableEq, Inhabited, Repr, Hashable

namespace Val

def ofJson (j : Json) : Val := ⟨j.compress⟩

def null : Val := ⟨"null"⟩

def isNull (v : Val) : Bool := v.json == "null"

def str (s : String) : Val := ofJson (.str s)

def int (n : Int) : Val := ofJson (.num ⟨n, 0⟩)

def bool (b : Bool) : Val := ofJson (.bool b)

def toJson (v : Val) : Json := (Json.parse v.json).toOption.getD .null

theorem isNull_iff {v : Val} : v.isNull = true ↔ v = null := by
  obtain ⟨json⟩ := v
  simp [isNull, null]

end Val

instance : ToJson Val := ⟨Val.toJson⟩
instance : FromJson Val := ⟨fun j => .ok (Val.ofJson j)⟩

end LeanUnit
