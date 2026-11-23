import LeanUnit

open Lean LeanUnit

namespace Model.Interrupt

def streamPrefix : String := "v1:middleware_agent_stream:"

def isStream (id : String) : Bool := id.startsWith streamPrefix

structure Interrupt where
  id : String
  name : String
  reason : Val
  response : Val
deriving DecidableEq, Repr, ToJson, FromJson

structure Pending where
  assistant_message : Val
  completed_tool_results : List Val
deriving DecidableEq, Repr, ToJson, FromJson

structure State where
  interrupts : Dict Interrupt
  context : Dict Val
  activated : Bool
  pending_tool_execution : Option Pending
  _version : Nat
deriving DecidableEq, Repr, ToJson, FromJson

structure Snapshot where
  interrupts : Dict Interrupt
  context : Dict Val
  activated : Bool
  pending_tool_execution : Option Pending
deriving DecidableEq, Repr

instance : ToJson Snapshot where
  toJson snapshot := Json.mkObj <|
    [("interrupts", toJson snapshot.interrupts), ("context", toJson snapshot.context),
     ("activated", toJson snapshot.activated)] ++
    match snapshot.pending_tool_execution with
    | some pending => [("pending_tool_execution", toJson pending)]
    | none => []

inductive Block where
  | response (interruptId : String) (response : Val)
  | text (text : String)
deriving DecidableEq, Repr

def Block.toJson : Block → Json
  | .response id answer =>
    Json.mkObj [("interruptResponse",
      Json.mkObj [("interruptId", Json.str id), ("response", Lean.toJson answer)])]
  | .text words => Json.mkObj [("text", Json.str words)]

instance : ToJson Block := ⟨Block.toJson⟩

def Block.isResponse : Block → Bool
  | .response _ _ => true
  | .text _ => false

inductive Prompt where
  | text (text : String)
  | blocks (items : List Block)
deriving DecidableEq, Repr

instance : ToJson Prompt where
  toJson
    | .text words => Json.str words
    | .blocks items => Json.arr (items.map Lean.toJson).toArray

def notStream (id : String) (_ : Interrupt) : Bool := !isStream id

def keepAfterToolCycle (id : String) (interrupt : Interrupt) : Bool :=
  isStream id && !interrupt.response.isNull

def responsesVal (items : List Block) : Val := Val.ofJson (Json.arr (items.map Lean.toJson).toArray)

def applyResponses (interrupts : Dict Interrupt) : List Block → Except (String × Dict Interrupt) (Dict Interrupt)
  | [] => .ok interrupts
  | .text _ :: rest => applyResponses interrupts rest
  | .response id answer :: rest =>
    match interrupts.get? id with
    | none => .error ("KeyError", interrupts)
    | some interrupt =>
      if answer.isNull then .error ("ValueError", interrupts)
      else applyResponses (interrupts.insert id { interrupt with response := answer }) rest

@[mirror "strands.interrupt:_InterruptState.activate"]
def activate (s : State) : Outcome State Unit :=
  .ok { s with activated := true, _version := s._version + 1 } ()

@[mirror "strands.interrupt:_InterruptState.deactivate"]
def deactivate (s : State) : Outcome State Unit :=
  .ok { s with interrupts := Dict.empty, context := Dict.empty, activated := false,
               pending_tool_execution := none, _version := s._version + 1 } ()

@[mirror "strands.interrupt:_InterruptState.end_tool_cycle"]
def end_tool_cycle (s : State) : Outcome State Unit :=
  .ok { s with interrupts := s.interrupts.filter keepAfterToolCycle, context := Dict.empty, activated := false,
               pending_tool_execution := none, _version := s._version + 1 } ()

@[mirror "strands.interrupt:_InterruptState.end_interrupt_cycle"]
def end_interrupt_cycle (s : State) : Outcome State Unit :=
  if s.interrupts.keys.all (fun id => !isStream id) then .ok s ()
  else .ok { s with interrupts := s.interrupts.filter notStream, _version := s._version + 1 } ()

@[mirror "strands.interrupt:_InterruptState.resume"]
def resume (s : State) (prompt : Prompt) : Outcome State Unit :=
  if !s.activated then .ok s ()
  else match prompt with
    | .text _ => .raise "TypeError" s
    | .blocks items =>
      if !items.all Block.isResponse then .raise "TypeError" s
      else match applyResponses s.interrupts items with
        | .error (exc, changed) => .raise exc { s with interrupts := changed }
        | .ok updated =>
          .ok { s with interrupts := updated, context := s.context.insert "responses" (responsesVal items),
                       _version := s._version + 1 } ()

@[mirror "strands.interrupt:_InterruptState.set_pending_tool_results"]
def set_pending_tool_results (s : State) (results : List Val) : Outcome State Unit :=
  match s.pending_tool_execution with
  | none => .ok s ()
  | some pending =>
    .ok { s with pending_tool_execution := some { pending with completed_tool_results := results },
                 _version := s._version + 1 } ()

def snapshot (s : State) : Snapshot :=
  { interrupts := if s.activated then s.interrupts else s.interrupts.filter notStream
    context := s.context
    activated := s.activated
    pending_tool_execution := s.pending_tool_execution }

@[mirror "strands.interrupt:_InterruptState.to_dict"]
def to_dict (s : State) : Outcome State Snapshot := .ok s (snapshot s)

@[mirror "strands.interrupt:_InterruptState._get_version"]
def _get_version (s : State) : Outcome State Nat := .ok s s._version

end Model.Interrupt
