State: IDLE
Task: -
Planner: -
Builder: -
Verifier: -
Strike: 0
Cursor: -

# Spec & Task Index
Goal: Isolate Read Aloud (`window.speechSynthesis`) per tab so pausing/playing across multiple MarkAu tabs or external Read Aloud never leaks, replays, pauses, or hijacks another tab's speech queue.
Env: Win11 / PowerShell. Scopes: src/speech/tts.js, src/core/multi-tab.js, tests/speech/tts-playback.test.js. Verify: npm run check && npm run build.
Rules: RED-GREEN-VERIFY (LAW II.4). Zero-LaTeX in *.md. No new deps. Preserve comments/docstrings. Never edit .harness/*.md.

## Index
- [x] T01 fix: isolate per-tab speechSynthesis ownership and cross-tab pause/resume

## T01 fix: isolate per-tab speechSynthesis ownership and cross-tab pause/resume
Intent: `window.speechSynthesis` is a browser-global singleton queue. Currently: (1) `pause()` leaves paused utterances in the global queue, and `play()` blindly calls `api.resume()` whenever `api.paused` is true — resuming another tab's speech or leaking Tab A's paused audio when Tab B calls `safeCancelSpeech()` (`resume()` + `cancel()`); (2) `pauseForOtherTab()` and `onerror('interrupted')` call `window.speechSynthesis.pause()`, which pauses the newly active tab/external Read Aloud; (3) `announceNarrationStart()` is skipped when `pauseOtherTabs` is false, so paused tabs never release their queue ownership; (4) `reconcileWithSpeechApi()` mistakes another tab's `api.speaking`/`api.pending`/`api.paused` for this tab's own speech and either calls `api.resume()` or restarts this tab when the other tab stops; (5) `stop()` on an idle tab calls `safeCancelSpeech()`, cancelling another tab's active speech.
Scope: src/speech/tts.js, src/core/multi-tab.js, tests/speech/tts-playback.test.js
Target: src/speech/tts.js:100-106,1523-1535,1665-1710,1744-1870,1986-2084,2157-2168; src/core/multi-tab.js:15-77; tests/speech/tts-playback.test.js
Symbols: tts.js: ownsPausedUtterance (new), releasePausedUtterance (new), pauseLocally (new), speakFromWord, play, pause, pauseForOtherTab, stop, reconcileWithSpeechApi, initPlaybackWatchdog; multi-tab.js: TAB_ID (new), announceNarrationStart, onOtherTabNarrationStart
Contract:
1. Track `ownsPausedUtterance` (true only when this tab called `api.pause()` and still owns its paused utterance). Reset to false on `stop()`, `finishPlayback()`, `speakFromWord()`, `onend`, `onerror`, `releasePausedUtterance()`, and `onOtherTabNarrationStart`.
2. In `play()`: only call `api.resume()` when `isPaused && ownsPausedUtterance && api.paused`; otherwise re-speak from `currentWordIndex` via `speakFromWord()`.
3. Always call `announceNarrationStart()` in `speakFromWord()` and when resuming in `play()` (with `from: TAB_ID` in `multi-tab.js` BroadcastChannel payload so a tab ignores its own messages).
4. In `onOtherTabNarrationStart` handler (`handleOtherTabNarrationStart` / `pauseForOtherTab`):
   - If `isPaused`: release `ownsPausedUtterance = false`, `currentSessionId++`, `teardownSession()`, `clearStartWatchdog()` (do NOT touch `window.speechSynthesis`).
   - If `isPlaying && !isPaused && getSettings().pauseOtherTabs === true`: `currentSessionId++`, mark `liveUtterances` `__canceled = true`, `teardownSession()`, `clearStartWatchdog()`, `ownsPausedUtterance = false`, `isPaused = true`, `notifyState({ isPlaying: true, isPaused: true, reason: 'other-tab' })` — NEVER call `window.speechSynthesis.pause()`.
5. On `visibilitychange` when `document.hidden && isPaused && ownsPausedUtterance`: release this tab's paused utterance from the global queue (`ownsPausedUtterance = false`, `currentSessionId++`, `teardownSession()`, `cancelEngine()`) while preserving `isPaused = true` and `currentWordIndex`.
6. On `utterance.onerror` with `event.error === 'interrupted'` and `isPlaying && !isStarting`: pause locally (`pauseLocally()`, no `window.speechSynthesis.pause()`).
7. In `reconcileWithSpeechApi()`:
   - Only call `api.resume()` for `api.paused && !isPaused && !document.hidden` when `liveUtterances.size > 0`.
   - When `api.speaking || api.pending` and `liveUtterances.size === 0 && pumpTimer === null && speakDebounceTimer === null`: this tab no longer owns the engine — call `pauseLocally()` instead of `noteProgress()` or restarting.
8. In `stop()`: only call `safeCancelSpeech()` if this tab actually holds or is starting speech (`isPlaying || isPaused || isStarting || liveUtterances.size > 0 || ownsPausedUtterance`).
Risks: Single-tab pause+resume without switching tabs must still call `api.resume()` without re-tokenizing (existing test `resumes the same utterance without re-tokenizing after a scroll`).
Command: npm run check && npm run build
Tests:
- RED 1: Tab A paused, then another tab announces narration start (even with `pauseOtherTabs: false`) -> Tab A's subsequent `play()` must re-speak Tab A (`speak` called) instead of calling `api.resume()` on the other tab's paused speech.
- RED 2: Tab A playing with `pauseOtherTabs: true`, another tab starts -> Tab A pauses locally (`isSpeechPaused() === true`, `reason: 'other-tab'`) WITHOUT calling `window.speechSynthesis.pause()`.
- RED 3: Tab A playing, interrupted by external Read Aloud (`onerror('interrupted')`) -> Tab A pauses locally WITHOUT calling `window.speechSynthesis.pause()`.
- RED 4: Tab A playing, another tab takes over (`liveUtterances` cleared / external speech active in `api.speaking`), watchdog `reconcileWithSpeechApi()` runs -> Tab A pauses locally instead of hijacking playback.
- RED 5: Idle tab calling `stop()` does NOT call `window.speechSynthesis.cancel()`.
Steps:
- [x] RED: add multi-tab/external-speech isolation tests in `tests/speech/tts-playback.test.js` -> run `npm run check` and confirm they fail.
- [x] GREEN: implement `TAB_ID` guard in `src/core/multi-tab.js` and per-tab ownership/isolation fixes in `src/speech/tts.js`.
- [x] VERIFY: run `npm run check && npm run build` -> all tests and build pass.
