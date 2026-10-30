import { describe, expect, it } from 'vitest';
import {
  frameLevel,
  shownStatus,
  initialVoiceSessionState,
  latestLines,
  voiceSessionReducer,
  type VoiceSessionAction,
  type VoiceSessionState,
} from './useVoiceSession';

const run = (actions: VoiceSessionAction[], from: VoiceSessionState = initialVoiceSessionState) =>
  actions.reduce(voiceSessionReducer, from);

const tx = (id: string, speaker: 'user' | 'assistant', text: string, final: boolean) =>
  ({ type: 'transcript', transcript: { id, speaker, text, final } }) as const;

describe('voice session reducer', () => {
  it('moves through states and revises a line in place by id', () => {
    const state = run([
      { type: 'start' },
      { type: 'ready', liveCaptions: false, working: true },
      { type: 'state', state: 'user_speaking' },
      tx('k:1', 'user', 'hel', false),
      tx('k:1', 'user', 'hello', true),
    ]);
    expect(state.status).toBe('user_speaking');
    expect(state.liveCaptions).toBe(false);
    expect(state.working).toBe(true);
    expect(state.transcripts).toEqual([{ id: 'k:1', speaker: 'user', text: 'hello', final: true }]);
  });

  it('never lets a late live update revert a final line', () => {
    const state = run([tx('k:1', 'user', 'final words', true), tx('k:1', 'user', 'fin', false)]);
    expect(state.transcripts[0]).toMatchObject({ text: 'final words', final: true });
  });

  it('tracks whether Suzent is working, and an error clears it', () => {
    let state = run([{ type: 'start' }, { type: 'working', active: true }]);
    expect(state.working).toBe(true);
    state = voiceSessionReducer(state, { type: 'error', key: 'voice.errors.session_error' });
    expect(state).toMatchObject({ status: 'error', working: false });
  });

  it('ignores late server states after the call ended or failed', () => {
    expect(run([{ type: 'state', state: 'speaking' }]).status).toBe('idle');
    const failed = run([{ type: 'start' }, { type: 'error', key: 'x' }]);
    expect(voiceSessionReducer(failed, { type: 'state', state: 'listening' }).status).toBe('error');
  });

  it('a server close ends the call but keeps an error visible', () => {
    expect(run([{ type: 'start' }, { type: 'closed' }])).toEqual(initialVoiceSessionState);
    const failed = run([{ type: 'start' }, { type: 'error', key: 'x' }, { type: 'closed' }]);
    expect(failed.status).toBe('error');
  });

  it('starts and stops clean, and bounds the line buffer', () => {
    const busy = run(Array.from({ length: 50 }, (_, i) => tx(`k:${i}`, 'user', `l${i}`, true)));
    expect(busy.transcripts).toHaveLength(20);
    expect(busy.transcripts.at(-1)?.text).toBe('l49');
    expect(voiceSessionReducer(busy, { type: 'start' }).transcripts).toEqual([]);
    expect(voiceSessionReducer(busy, { type: 'stop' })).toEqual(initialVoiceSessionState);
  });
});

describe('shownStatus', () => {
  const call = run([{ type: 'start' }, { type: 'state', state: 'speaking' }]);

  it('stays speaking while a reply sent faster than real time is still playing', () => {
    const generated = run(
      [
        { type: 'playback', playing: true },
        { type: 'state', state: 'listening' },
      ],
      call
    );
    expect(generated.status).toBe('listening');
    expect(shownStatus(generated)).toBe('speaking');
    const played = voiceSessionReducer(generated, { type: 'playback', playing: false });
    expect(shownStatus(played)).toBe('listening');
  });

  it('shows the user taking the turn even while the reply still plays', () => {
    const playing = run([{ type: 'playback', playing: true }], call);
    expect(
      shownStatus(voiceSessionReducer(playing, { type: 'state', state: 'user_speaking' }))
    ).toBe('user_speaking');
    expect(shownStatus(voiceSessionReducer(playing, { type: 'state', state: 'thinking' }))).toBe(
      'thinking'
    );
  });

  it('a new call starts with nothing playing', () => {
    const playing = run([{ type: 'playback', playing: true }], call);
    expect(voiceSessionReducer(playing, { type: 'start' }).playing).toBe(false);
    expect(voiceSessionReducer(playing, { type: 'stop' }).playing).toBe(false);
  });
});

describe('latestLines', () => {
  it('returns the newest line from each speaker', () => {
    const { transcripts } = run([
      tx('1', 'user', 'first', true),
      tx('2', 'assistant', 'reply', true),
      tx('3', 'user', 'second', false),
    ]);
    const { user, assistant } = latestLines(transcripts);
    expect(user?.text).toBe('second');
    expect(assistant?.text).toBe('reply');
    expect(latestLines([])).toEqual({ user: null, assistant: null });
  });
});

describe('voiceSessionReducer interrupted', () => {
  it('settles a cut-off assistant caption but leaves user lines alone', () => {
    let state = voiceSessionReducer(initialVoiceSessionState, { type: 'start' });
    state = voiceSessionReducer(state, {
      type: 'transcript',
      transcript: { id: 'u', speaker: 'user', text: '你好', final: false },
    });
    state = voiceSessionReducer(state, {
      type: 'transcript',
      transcript: { id: 'a', speaker: 'assistant', text: '我正在', final: false },
    });
    state = voiceSessionReducer(state, { type: 'interrupted' });
    expect(state.transcripts.map((line) => line.final)).toEqual([false, true]);
    // A late partial for the settled line cannot revive it.
    state = voiceSessionReducer(state, {
      type: 'transcript',
      transcript: { id: 'a', speaker: 'assistant', text: '我正在说', final: false },
    });
    expect(state.transcripts[1]).toMatchObject({ text: '我正在', final: true });
  });

  it('is a no-op without a live assistant line', () => {
    const state = voiceSessionReducer(initialVoiceSessionState, { type: 'start' });
    expect(voiceSessionReducer(state, { type: 'interrupted' })).toBe(state);
  });
});

describe('frameLevel', () => {
  const tone = (amplitude: number) =>
    Float32Array.from({ length: 480 }, (_, i) => amplitude * Math.sin(i / 3));
  it('is 0 for silence and empty frames', () => {
    expect(frameLevel(new Float32Array(480))).toBe(0);
    expect(frameLevel(new Float32Array(0))).toBe(0);
  });
  it('never returns NaN, which would freeze the meter', () => {
    expect(frameLevel(Float32Array.of(0.1, NaN))).toBe(0);
  });
  it('rises with loudness and saturates at 1', () => {
    const quiet = frameLevel(tone(0.003));
    const speech = frameLevel(tone(0.1));
    expect(quiet).toBeLessThan(0.2);
    expect(speech).toBeGreaterThan(0.6);
    expect(frameLevel(tone(1))).toBe(1);
  });
});
