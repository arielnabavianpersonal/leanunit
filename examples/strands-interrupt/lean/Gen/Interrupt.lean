import Model.Interrupt

open Lean LeanUnit Model.Interrupt

namespace Gen.Interrupt

def idPool : List String :=
  ["a", "b", "tool:1", streamPrefix ++ "a", streamPrefix ++ "b", streamPrefix]

def genId : Gen String :=
  Gen.frequency (Gen.elements "a" idPool)
    [(5, Gen.elements "a" idPool), (1, Gen.string), (1, (streamPrefix ++ ·) <$> Gen.string)]

def genResponse : Gen Val :=
  Gen.frequency (pure Val.null) [(2, pure Val.null), (3, Sample.sample)]

def genInterrupt (id : String) : Gen Interrupt := do
  pure { id, name := ← Gen.string, reason := ← Sample.sample, response := ← genResponse }

def genInterrupts : Gen (Dict Interrupt) := do
  let ids ← Gen.listOf genId
  let pairs ← ids.mapM fun id => do pure (id, ← genInterrupt id)
  pure (Dict.ofList pairs).sorted

instance : Sample Pending :=
  ⟨do pure { assistant_message := ← Sample.sample, completed_tool_results := ← Sample.sample }⟩

instance : Sample State :=
  ⟨do pure { interrupts := ← genInterrupts, context := ← Sample.sample, activated := ← Gen.bool,
             pending_tool_execution := ← Sample.sample, _version := ← Gen.nat }⟩

def genBlock : Gen Block :=
  Gen.frequency (pure (.text "hi"))
    [(6, do pure (.response (← genId) (← genResponse))), (1, Block.text <$> Gen.string)]

instance : Sample Prompt :=
  ⟨Gen.frequency (pure (.blocks []))
    [(1, Prompt.text <$> Gen.string), (6, Prompt.blocks <$> Gen.listOf genBlock)]⟩

end Gen.Interrupt
