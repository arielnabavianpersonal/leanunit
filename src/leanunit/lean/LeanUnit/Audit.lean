import Lean
import LeanUnit.Attr

open Lean Elab Command

namespace LeanUnit.Audit

def projectRoots : List Name := [`Laws, `Model, `Proofs, `Gen]

def moduleOf? (env : Environment) (name : Name) : Option Name :=
  (env.getModuleIdxFor? name).map fun idx => env.header.moduleNames[idx.toNat]!

def isProjectModule (module : Name) : Bool := projectRoots.contains module.getRoot

def isProjectConst (env : Environment) (name : Name) : Bool :=
  match moduleOf? env name with
  | some module => isProjectModule module
  | none => false

def byName (a b : Name) : Bool := a.toString < b.toString

def describe (info : ConstantInfo) : String :=
  match info with
  | .defnInfo d => s!"def {d.name} : {d.type} := {d.value}"
  | .thmInfo t => s!"theorem {t.name} : {t.type}"
  | .opaqueInfo o => s!"opaque {o.name} : {o.type} := {o.value}"
  | .axiomInfo a => s!"axiom {a.name} : {a.type}"
  | .inductInfo i => s!"inductive {i.name} : {i.type} with {i.ctors}"
  | .ctorInfo c => s!"ctor {c.name} : {c.type}"
  | .recInfo r => s!"rec {r.name} : {r.type}"
  | .quotInfo q => s!"quot {q.name} : {q.type}"

def dependencies (info : ConstantInfo) : Array Name :=
  let fromBody := match info with
    | .defnInfo d => d.value.getUsedConstants
    | .opaqueInfo o => o.value.getUsedConstants
    | .inductInfo i => i.ctors.toArray
    | _ => #[]
  (info.type.getUsedConstants ++ fromBody).qsort byName

structure Closure where
  hashInput : String
  covers : Array String

partial def lawClosure (env : Environment) (law : Name) : Closure := Id.run do
  let mut seen : NameSet := {}
  let mut queue : Array Name := #[law]
  let mut parts : Array String := #[]
  let mut covers : Array String := #[]
  let mut index := 0
  while index < queue.size do
    let name := queue[index]!
    index := index + 1
    if seen.contains name then continue
    seen := seen.insert name
    if let some target := mirrorAttr.getParam? env name then
      parts := parts.push s!"mirror {name} -> {target}"
      covers := covers.push target
    else if isProjectConst env name then
      match env.find? name with
      | some info =>
        parts := parts.push (describe info)
        queue := queue ++ dependencies info
      | none => parts := parts.push s!"missing {name}"
  return { hashInput := "\n".intercalate parts.toList, covers := covers.qsort (· < ·) }

partial def reachable (env : Environment) (roots : Array Name) : Array ConstantInfo := Id.run do
  let mut seen : NameSet := {}
  let mut queue := roots
  let mut found : Array ConstantInfo := #[]
  let mut index := 0
  while index < queue.size do
    let name := queue[index]!
    index := index + 1
    if seen.contains name || !isProjectConst env name then continue
    seen := seen.insert name
    if let some info := env.find? name then
      found := found.push info
      queue := queue ++ dependencies info
  return found

def forbiddenReasons (env : Environment) (info : ConstantInfo) : List String :=
  let name := info.name
  (if (Compiler.implementedByAttr.getParam? env name).isSome then ["implemented_by"] else []) ++
  (if isExtern env name then ["extern"] else []) ++
  (if info.isUnsafe then ["unsafe"] else []) ++
  (if info.isPartial then ["partial"] else [])

def lawOfStatement? : Expr → Option (Name × Bool)
  | .const name [] => some (name, false)
  | .app (.const ``Not []) (.const name []) => some (name, true)
  | _ => none

def explicitArity : Expr → Nat
  | .forallE _ _ body .default => explicitArity body + 1
  | .forallE _ _ body _ => explicitArity body
  | _ => 0

def lawProblem? : ConstantInfo → Option String
  | .defnInfo d =>
    if !d.levelParams.isEmpty then some "a law must not have universe parameters"
    else if d.type != .sort .zero then some "a law must be a definition of type Prop"
    else none
  | _ => some "a law must be a definition of type Prop"

structure ProofReport where
  name : String
  axioms : Array String
deriving ToJson

structure LawReport where
  name : String
  module : String
  hashInput : String
  covers : Array String
  proofs : Array ProofReport
  refutations : Array ProofReport
  problem : Option String
deriving ToJson

structure MirrorReport where
  name : String
  module : String
  target : String
  arity : Nat
deriving ToJson

structure ForbiddenReport where
  name : String
  reasons : Array String
deriving ToJson

structure Report where
  toolchain : String
  modules : Array String
  laws : Array LawReport
  mirrors : Array MirrorReport
  forbidden : Array ForbiddenReport
deriving ToJson

def moduleString (env : Environment) (name : Name) : String :=
  ((moduleOf? env name).map toString).getD ""

def proofReport (name : Name) : CoreM ProofReport := do
  let axioms ← collectAxioms name
  return { name := name.toString, axioms := (axioms.map toString).qsort (· < ·) }

def makeReport : CoreM Report := do
  let env ← getEnv
  let project := (env.constants.fold (init := #[]) fun acc name info =>
    if isProjectConst env name then acc.push info else acc).qsort fun a b => byName a.name b.name
  let lawNames := project.filter (fun info => lawAttr.hasTag env info.name) |>.map (·.name)
  let mirrorInfos := project.filter fun info => (mirrorAttr.getParam? env info.name).isSome
  let mut proofs : NameMap (Array ProofReport) := {}
  let mut refutations : NameMap (Array ProofReport) := {}
  for info in project do
    if let .thmInfo t := info then
      if let some (law, refutes) := lawOfStatement? t.type then
        if lawNames.contains law then
          let report ← proofReport t.name
          if refutes then
            refutations := refutations.insert law (((refutations.find? law).getD #[]).push report)
          else
            proofs := proofs.insert law (((proofs.find? law).getD #[]).push report)
  let laws := lawNames.map fun law =>
    let closure := lawClosure env law
    { name := law.toString
      module := moduleString env law
      hashInput := closure.hashInput
      covers := closure.covers
      proofs := (proofs.find? law).getD #[]
      refutations := (refutations.find? law).getD #[]
      problem := (env.find? law).bind lawProblem? : LawReport }
  let mirrors := mirrorInfos.map fun info =>
    { name := info.name.toString
      module := moduleString env info.name
      target := (mirrorAttr.getParam? env info.name).getD ""
      arity := explicitArity info.type : MirrorReport }
  let checked := reachable env (lawNames ++ mirrorInfos.map (·.name))
  let forbidden := checked.filterMap fun info =>
    match forbiddenReasons env info with
    | [] => none
    | reasons => some { name := info.name.toString, reasons := reasons.toArray : ForbiddenReport }
  let modules := (env.header.moduleNames.filter isProjectModule).map toString
  return { toolchain := Lean.versionString, modules, laws, mirrors,
           forbidden := forbidden.qsort fun a b => a.name < b.name }

elab "#leanunit_audit" : command => do
  let report ← liftCoreM makeReport
  IO.println s!"LEANUNIT_AUDIT {(toJson report).compress}"

end LeanUnit.Audit
