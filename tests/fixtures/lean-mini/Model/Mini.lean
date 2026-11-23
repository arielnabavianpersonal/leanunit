import LeanUnit

open LeanUnit

namespace Model.Mini

@[mirror "mini:inc"]
def inc (n : Nat) : Outcome Unit Nat := .ok () (n + 1)

def helper (n : Nat) : Prop := n > 0

def fastDouble (n : Nat) : Nat := 2 * n

@[implemented_by fastDouble]
def double (n : Nat) : Nat := n + n

end Model.Mini
