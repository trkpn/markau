# HANDOFF.md - Read-Only Context Transfer Contract

RULES (`.harness/LAW.md`):
Immutable: Never edit `.harness/HANDOFF.md`. Write ephemeral snapshots strictly to `.harness/runtime/_HANDOFF.md` (gitignored; copy Sections 0-5 if absent). Decoupled from `_ACTIVE.md` and `.harness/runtime/_SPAWN.md` (never used for `FLOW.md`). Applies to `STAGE` and `ASK` sessions.

Protocol (Valid for `HANDOFF.md` or `_HANDOFF.md`):
- Save (`--save`, or bare in active chat when capturing context): Summarize Intent, Agreed/Discarded Decisions, Touchpoints, Nuances, and Immediate Next Direction, then write/overwrite `.harness/runtime/_HANDOFF.md`.
- Resume (`--resume`, or bare `HANDOFF.md` / `_HANDOFF.md` when loading snapshot): Read `.harness/runtime/_HANDOFF.md` read-only, absorb context, `Active Track`, and `Conversation Mode` without re-reading raw history, and continue immediately. Never clear/delete `.harness/runtime/_HANDOFF.md` on read and never write `_LOG.jsonl` (safe for concurrent Coding Agents).

## 0. Transfer Metadata
- Timestamp: `<YYYY-MM-DD HH:MM>`
- Source Session / Tool: `<Antigravity | Claude Code | ZCode | OpenCode | Codex | DeepSeek Harness | Other>`
- Active Track: `<STAGE | ASK>`
- Conversation Mode: `<ASK / Q&A | Oracley / Planning | Code Implementation | Debugging>`

## 1. Core Topic & Context Intent
- Central Theme: `<What this discussion/session is fundamentally about>`
- User Intent & Perspective: `<Core concerns, preferences, or angles raised by the Founder>`

## 2. Agreed Decisions & Conclusions
- Consensus Reached:
  - `<Conclusion 1: What was agreed upon and why>`
  - `<Conclusion 2: Specific approach or philosophy chosen>`
- Discarded / Non-Viable Options:
  - `<What was considered but rejected, with reasons to avoid re-hashing>`

## 3. Current Progress & Touchpoints
- Covered So Far: `<Points discussed, files referenced, or concepts analyzed>`
- Artifacts / References: `<Key files, links, or documents in play>`

## 4. Nuances, Gotchas & Implicit Constraints
- Subtle Constraints: `<Unwritten rules, specific user preferences, or edge cases discussed>`
- Known Traps to Avoid: `<Assumptions that were proven wrong or flagged as overconfident>`

## 5. Immediate Next Direction
- Next Topic / Action: `<The exact question to explore, decision to make, or action to execute next>`
