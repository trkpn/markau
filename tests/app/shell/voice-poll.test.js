import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { installBrowserStubs } from '../../helpers.js';
import { getAvailableVoices, setVoice } from '@/speech/tts.js';

/**
 * Minimal fake elements: enough surface for the header controls to wire
 * themselves up and for the voice options to be counted and read back.
 */
const h = vi.hoisted(() => {
  const makeEl = (id) => {
    let html = '';
    const node = {
      id,
      disabled: false,
      title: '',
      value: '',
      textContent: '',
      selectedIndex: -1,
      label: '',
      children: [],
      options: [],
      classList: { toggle() {}, add() {}, remove() {} },
      setAttribute() {},
      addEventListener() {},
      removeEventListener() {},
      querySelector: () => null,
      appendChild(child) {
        node.children.push(child);
        node.options.push(child);
      }
    };
    Object.defineProperty(node, 'innerHTML', {
      get: () => html,
      set: (next) => {
        html = next;
        node.children.length = 0;
        node.options.length = 0;
      }
    });
    return node;
  };

  const el = {
    btnPlay: makeEl('btn-play'),
    btnStop: makeEl('btn-stop'),
    voiceSelect: makeEl('voice-select'),
    rateSlider: makeEl('rate-slider'),
    rateBadge: makeEl('rate-badge'),
    btnMic: makeEl('btn-mic'),
    btnTheme: makeEl('btn-theme'),
    btnPrint: makeEl('btn-print'),
    btnSyncScroll: makeEl('btn-sync-scroll'),
    settingsVoiceSelect: makeEl('settings-voice-select')
  };

  /** What the stubbed engine reports on the next read. */
  const state = { availableVoices: [] };

  return { makeEl, el, state };
});

vi.mock('@/app/shell/dom.js', () => ({ el: h.el }));
vi.mock('@/speech/tts.js', () => ({
  stop: vi.fn(),
  setRate: vi.fn(),
  setVoice: vi.fn(),
  getAvailableVoices: vi.fn(async () => h.state.availableVoices),
  onTTSStateChange: vi.fn(),
  initPlaybackWatchdog: vi.fn()
}));
vi.mock('@/speech/stt.js', () => ({
  toggleListening: vi.fn(),
  isSTTSupported: () => false,
  insertTextAtCursor: vi.fn(),
  onSTTStateChange: vi.fn()
}));
vi.mock('@/app/shell/status.js', () => ({
  setBaseMessage: vi.fn(),
  setMessage: vi.fn(),
  setNarrationState: vi.fn(),
  setDictationState: vi.fn(),
  setNetworkState: vi.fn()
}));
vi.mock('@/app/editor/print.js', () => ({ printDocument: vi.fn() }));
vi.mock('@/app/preview/narration.js', () => ({
  toggleNarration: vi.fn(),
  cancelPendingStart: vi.fn()
}));
vi.mock('@/app/shell/toolbar.js', () => ({ refreshToolbarDensity: vi.fn() }));

installBrowserStubs();

/**
 * ============================================================================
 * VOICE SELECTOR POLLING
 * ============================================================================
 * A device without synthesis voices must not be polled forever: after 30
 * failed seconds the selector reports the missing voices and stops. These
 * tests drive `initControls` with a speech engine that never delivers
 * voices, so the header around the selector is exercised while the engine
 * itself is stubbed.
 * ============================================================================
 */

/**
 * Extra stub surface the header controls need beyond helpers.js: the theme
 * writes an attribute on <html>, the voice options are built with
 * document.createElement, and the speech engine lives on `window`.
 */
globalThis.document.documentElement.setAttribute = () => {};
globalThis.document.createElement = h.makeEl;
globalThis.document.removeEventListener = () => {};
globalThis.window.speechSynthesis = {
  getVoices: () => [],
  addEventListener: () => {},
  removeEventListener: () => {}
};

const { initControls } = await import('@/app/shell/controls.js');

describe('voice selector polling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('gives up after 30 failed ticks and marks the voices missing', async () => {
    await initControls();
    await vi.advanceTimersByTimeAsync(0);

    // Nothing arrived yet: the selectors show the loading placeholder and
    // exactly one engine read has happened.
    expect(h.el.voiceSelect.children[0].textContent).toBe('Loading voices…');
    expect(getAvailableVoices.mock.calls.length).toBe(1);

    await vi.advanceTimersByTimeAsync(31_000);

    // The poll gave up: the selectors report the device as voiceless...
    expect(h.el.voiceSelect.children[0].textContent).toBe('No synthesis voices on this device');
    expect(h.el.settingsVoiceSelect.children[0].textContent).toBe(
      'No synthesis voices on this device'
    );

    // ...and stopped: advancing further never reads the engine again.
    const callsAfter = getAvailableVoices.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5_000);
    expect(getAvailableVoices.mock.calls.length).toBe(callsAfter);
  });

  it('stops polling as soon as voices arrive', async () => {
    await initControls();
    await vi.advanceTimersByTimeAsync(0);
    expect(getAvailableVoices.mock.calls.length).toBe(1);

    h.state.availableVoices = [
      { name: 'Microsoft Aria Online (Natural) - English (United States)', lang: 'en-US' }
    ];
    await vi.advanceTimersByTimeAsync(2_000);

    const group = h.el.voiceSelect.children[0];
    expect(group.label).toBe('🇺🇸 English Voices');
    expect(group.children[0].value).toBe(h.state.availableVoices[0].name);
    expect(setVoice).toHaveBeenCalled();

    const callsAfter = getAvailableVoices.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5_000);
    expect(getAvailableVoices.mock.calls.length).toBe(callsAfter);
  });
});
