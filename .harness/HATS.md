# HATS.md - Technical Thinking Protocol

RULES (`.harness/LAW.md`):
1. Session-First & Flags: Invoke via `HATS.md [--stage] [-<flag>] [query]`. Without `--stage`, bind strictly to current Session Context (plus `[query]` if given; if new session has no context, ask). Use `--stage` to target `_ACTIVE.md`.
2. Anti-Overconfidence: Agents must NEVER claim a proposal is infallible. Use the Failure Vector to challenge assumptions.
3. Pragmatic Engineering Focus: Check code, baselines, or `_MEM.jsonl` only as relevant to the bound target (never hijack Session Context with unrelated files).
4. Output & Read-Only (Zero 2x Bloat): Keep code read-only (ASK|STAGE|FLOW). Active STAGE: record notes in `_ACTIVE.md`; reply <= 3 lines + pointer. ASK: 1x structured concise reply in chat (use HANDOFF.md --save to persist). Hand pivots to AGENTS.md Auto-Route.

## The 5 Technical Analysis Vectors
- `(Default)` Balanced Synthesis: Multi-angle evaluation combining all relevant vectors into a recommended path.
- `-k` / `--risk` Failure & Risk Vector: What can break under load or edge conditions? Audit race conditions, nulls, failure modes, breaking changes, and invalid assumptions.
- `-p` / `--viable` Viability & Velocity Vector: What is the fastest viable path to working software? Identify direct solutions, minimal shims, and workable implementations without over-engineering.
- `-a` / `--struct` Structural Boundary Vector: How does this change affect the system 6 months from now? Enforce clean boundaries, decoupling, maintainability, and prevent technical debt.
- `-y` / `--yagni` Pruning & Scope Vector: What can we cut first? Reuse codebase, stdlib, or installed deps? Enforce YAGNI; skip unneeded code, new deps, and abstractions.
- `-d` / `--interface` Interface & DX Vector: How ergonomic and clear is this interface for callers? Audit developer experience, API readability, and cognitive load at call sites.
