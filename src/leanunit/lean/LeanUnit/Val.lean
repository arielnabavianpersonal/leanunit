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

def arr (items : List Val) : Val := ofJson (.arr (items.map toJson).toArray)

def obj (fields : List (String × Val)) : Val := ofJson (Json.mkObj (fields.map fun (key, value) => (key, value.toJson)))

def object (cls : String) (fields : List (String × Val)) : Val := obj (("__class__", str cls) :: fields)

def bytes (base64 : String) : Val := obj [("__bytes__", str base64)]

def enum (path : String) : Val := obj [("__enum__", str path)]

def callable (path : String) : Val := obj [("__callable__", str path)]

def float (text : String) : Val := obj [("__float__", str text)]

theorem isNull_iff {v : Val} : v.isNull = true ↔ v = null := by
  obtain ⟨json⟩ := v
  simp [isNull, null]

end Val

instance : ToJson Val := ⟨Val.toJson⟩
instance : FromJson Val := ⟨fun j => .ok (Val.ofJson j)⟩

end LeanUnit
