import LeanUnit.Gen

open Lean

namespace LeanUnit

structure Bytes where
  base64 : String
deriving DecidableEq, Inhabited, Repr, Hashable

namespace Bytes

def alphabet : List Char := "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".toList

def symbol (n : Nat) : Char := alphabet.getD (n % 64) 'A'

def encodeChars : List UInt8 → List Char
  | [] => []
  | [a] =>
    let n := a.toNat <<< 16
    [symbol (n >>> 18), symbol (n >>> 12), '=', '=']
  | [a, b] =>
    let n := (a.toNat <<< 16) + (b.toNat <<< 8)
    [symbol (n >>> 18), symbol (n >>> 12), symbol (n >>> 6), '=']
  | a :: b :: c :: rest =>
    let n := (a.toNat <<< 16) + (b.toNat <<< 8) + c.toNat
    symbol (n >>> 18) :: symbol (n >>> 12) :: symbol (n >>> 6) :: symbol n :: encodeChars rest

def ofList (data : List UInt8) : Bytes := ⟨String.ofList (encodeChars data)⟩

def ofString (text : String) : Bytes := ofList text.toUTF8.toList

end Bytes

instance : ToJson Bytes := ⟨fun bytes => Json.mkObj [("__bytes__", Json.str bytes.base64)]⟩

instance : FromJson Bytes := ⟨fun json => do pure ⟨← json.getObjValAs? String "__bytes__"⟩⟩

instance : Sample Bytes :=
  ⟨do
    let count ← Gen.natIn 0 (min (← Gen.size) 8)
    let data ← (List.range count).mapM fun _ => do pure (UInt8.ofNat (← Gen.natIn 0 255))
    pure (Bytes.ofList data)⟩

end LeanUnit
