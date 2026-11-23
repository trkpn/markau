# INTENT.md - Upstream Intent Ingestion Runbook

Bridge translating raw speech-to-text (STT), dictation, and briefs into bounded contracts.
Canonical Stage 1 (Intent -> Plan -> Build -> Verify): Mandatory standalone contract for STAGE; optional/inline for FLOW.

## 1. Operating Protocol
Execute on-demand via `INTENT.md [transcript or brief]` (bind strictly to input or Session Context; never pull unrelated `ACTIVE_*`):
1. STT Normalization:
   - Phonetics: Map phonetic transliterations to standard English tech terms (API, config, Docker, commit).
   - Glitch Detection: Detect STT predictive auto-replacements of jargon with incongruent words. Validate sentence engineering semantics. Reject hallucinations.
   - Disambiguation: Disentangle thinking-out-loud streams. Isolate mid-sentence pivots and self-corrections to extract final settled intent.
   - Segmentation: Convert run-on speech into structured requirements.
2. Confirmation Gate (Zero-Speculation):
   - Present Understanding Echo in chat before proceeding.
   - If ambiguous or distorted: HALT IMMEDIATELY. Invoke native question tool if available, or ask in plain text. Never guess.
   - Advance only upon explicit user confirmation (`OK`, `Yes`, or corrections; halt with `Next:` — `OK` to confirm, or reply corrections).
3. Boundaries: Define core problem, measurable KPI, and non-goals (Anti-Scope / YAGNI).
4. Output & Hand-Off: Map affected domains (`DATA`, `API`, `UI`, `SEC`, `OPS`) and emit `INTAKE CONTRACT` only. Hand back to `AGENTS.md` Auto-Route (never route tracks or write `_ACTIVE.md` directly), ending with `Next:` — `PLAN.md` (complex/gated) or `FLOW.md` (clear, local, low-risk).

## 2. Ingestion Schema (Echo)
```text
INTAKE CONTRACT:
- Decoded Intent: 1. <Normalized requirement> | 2. <Settled intent>
- Problem: <Core problem being solved>
- Proposed Outcome: <Measurable success KPI / target state>
- Affected Users & Systems: <DATA | API | UI | SEC | OPS | User roles>
- Constraints & Anti-Scope: <Hard limits, deferred items>
- Open Questions: <None | Blocking questions for user>
- Risk Traps: <Security, data, or performance traps>
```
