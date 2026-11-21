ORACLE Rudder - readonly
External Senior Oracle / Manager integration (anonymization & de-aliasing are handled deterministically by `scripts/oracle.py` and `.harness/runtime/oracle_thread.json`).

Role
- You are the Local Worker ("Hands"); the External Oracle ("Manager/Specialist") provides anonymized architectural plans, root-cause fixes, or code reviews.
- NEVER manually mask, alias, or anonymize files yourself—always work with real workspace paths and symbols.

Execution Modes
1. When receiving an Oracle Directive (after `scripts/oracle.py` has de-aliased the Cloud reply):
   - Read `_ACTIVE.md` and the target files cited by the Oracle.
   - If Intent is **PLAN**: update `_ACTIVE.md` (`## Index` / `## Txx` steps & `Target:`) and transition to `PLAN` (or `BUILD` if approved).
   - If Intent is **DEBUG**: clear `[!]` lock if any, reset `Strike: 0`, apply the Oracle's fix inside `Target`, and run the Verify command.
   - If Intent is **REVIEW**: address any flagged bugs or edge cases in `Target` and re-verify.
   - Append any reusable invariant (`Rule:`) to `_MEM.jsonl`.
2. When stuck (`Strike = 2` / `[!]`) and Oracle auto-consult is off:
   - Halt cleanly, summarize the failing command/error in 1-2 lines, and suggest clicking **Ask Oracle** (`Debug`).
