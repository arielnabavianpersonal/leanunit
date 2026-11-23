import Lean

open Lean

syntax (name := mirror) "mirror " str : attr

namespace LeanUnit

initialize lawAttr : TagAttribute ←
  registerTagAttribute `law "A LeanUnit law: a Prop definition that a human approves."

initialize mirrorAttr : ParametricAttribute String ←
  registerParametricAttribute {
    name := `mirror
    descr := "Links a model function to a code function, written as module:Qualname."
    getParam := fun _ stx => do
      match stx with
      | `(attr| mirror $target:str) => pure target.getString
      | _ => throwError "expected @[mirror \"module:Qualname\"]"
  }

end LeanUnit
