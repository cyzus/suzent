import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSpeechJob, SpeechQueue, type SpeechJob } from './speechPlayback';
import { LiveSpeechTracker } from './liveSpeech';
import type { AGUIPart } from '../types/agui';

function controlled(id: string) {
  let done: (blocked?: boolean) => void = () => {};
  const cleanup = vi.fn();
  const start = vi.fn((finish: (blocked?: boolean) => void) => {
    done = finish;
    return cleanup;
  });
  return {
    job: { id, start } as SpeechJob,
    start,
    cleanup,
    finish: (blocked = false) => done(blocked),
  };
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('speech queue', () => {
  it('serializes mixed speech, deduplicates automatic results and permits replay', () => {
    const queue = new SpeechQueue();
    const a = controlled('system'),
      b = controlled('api');
    queue.enqueue(a.job, true);
    queue.enqueue(b.job, true);
    queue.enqueue(a.job, true);
    expect(a.start).toHaveBeenCalledTimes(1);
    expect(b.start).not.toHaveBeenCalled();
    expect(queue.state('api')).toBe('queued');
    a.finish();
    expect(a.cleanup).toHaveBeenCalledOnce();
    expect(b.start).toHaveBeenCalledOnce();
    b.finish();
    queue.enqueue(a.job, true);
    expect(a.start).toHaveBeenCalledTimes(1);
    queue.enqueue(a.job);
    expect(a.start).toHaveBeenCalledTimes(2);
  });
  it('stops active and pending speech on chat change and ignores late completions', () => {
    const queue = new SpeechQueue();
    const a = controlled('a'),
      b = controlled('b');
    queue.enqueue(a.job);
    queue.enqueue(b.job);
    queue.reset();
    a.finish();
    expect(a.cleanup).toHaveBeenCalledOnce();
    expect(b.start).not.toHaveBeenCalled();
    expect(queue.state('a')).toBe('idle');
    expect(queue.state('b')).toBe('idle');
  });
  it('supports stopping queued speech and disabling autoplay without blocking manual playback', () => {
    const queue = new SpeechQueue();
    const a = controlled('a'),
      b = controlled('b');
    queue.enqueue(a.job);
    queue.enqueue(b.job);
    queue.stop('b');
    a.finish();
    expect(b.start).not.toHaveBeenCalled();
    queue.setAutoplay(false);
    queue.enqueue(b.job, true);
    expect(b.start).not.toHaveBeenCalled();
    queue.setAutoplay(true);
    queue.enqueue(b.job, true);
    expect(b.start).not.toHaveBeenCalled();
    queue.enqueue(b.job);
    expect(b.start).toHaveBeenCalledOnce();
  });
  it('reports browser autoplay rejection and releases the queue', async () => {
    const pause = vi.fn();
    vi.stubGlobal(
      'Audio',
      class {
        volume = 1;
        onended = null;
        onerror = null;
        play() {
          return Promise.reject(new Error('NotAllowedError'));
        }
        pause = pause;
        removeAttribute() {}
        load() {}
      }
    );
    const queue = new SpeechQueue();
    queue.enqueue(createSpeechJob({ speech_id: 'blocked' }, '/audio.mp3'), true);
    await Promise.resolve();
    expect(queue.state('blocked')).toBe('blocked');
    expect(pause).toHaveBeenCalledOnce();
    const next = controlled('next');
    queue.enqueue(next.job);
    expect(next.start).toHaveBeenCalledOnce();
  });
  it('waits for local system voices and cancels speech on reset', () => {
    vi.useFakeTimers();
    let voices: unknown[] = [];
    let changed = () => {};
    const synth = {
      getVoices: () => voices,
      addEventListener: (_: string, fn: () => void) => {
        changed = fn;
      },
      removeEventListener: vi.fn(),
      speak: vi.fn(),
      cancel: vi.fn(),
    };
    vi.stubGlobal('window', { speechSynthesis: synth });
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class {
        constructor(public text: string) {}
      }
    );
    const queue = new SpeechQueue();
    queue.enqueue(createSpeechJob({ speech_id: 'local', text: 'hello' }), true);
    expect(synth.speak).not.toHaveBeenCalled();
    voices = [{ localService: true, voiceURI: 'local', lang: 'en-US' }];
    changed();
    expect(synth.speak).toHaveBeenCalledOnce();
    queue.reset();
    vi.runAllTimers();
    expect(synth.cancel).toHaveBeenCalledOnce();
    expect(queue.state('local')).toBe('idle');
  });
});

const speech = (id: string): AGUIPart => ({
  type: 'tool',
  toolName: 'speak',
  toolCallId: id,
  output: '{}',
});
describe('live speech selection', () => {
  it('suppresses initial chat history but accepts later completions once across snapshot replay', () => {
    const tracker = new LiveSpeechTracker(true);
    expect(tracker.collect([speech('old')], 'run', true)).toEqual([]);
    expect(tracker.collect([speech('old'), speech('new')], 'run', false)).toEqual([speech('new')]);
    expect(tracker.collect([speech('old'), speech('new')], 'run', true)).toEqual([]);
    expect(tracker.collect([speech('third')], 'run', true)).toEqual([speech('third')]);
  });
  it('plays an immediate result from a user-started turn but not seeded approval history', () => {
    const tracker = new LiveSpeechTracker(false, [speech('before-approval')]);
    expect(tracker.collect([speech('before-approval'), speech('new')], 'run', true)).toEqual([
      speech('new'),
    ]);
  });
  it('does not play history when reentering a chat or refreshing', () => {
    expect(new LiveSpeechTracker(true).collect([speech('old')], 'run', true)).toEqual([]);
    expect(new LiveSpeechTracker(true).collect([speech('old')], 'run', true)).toEqual([]);
  });
});
