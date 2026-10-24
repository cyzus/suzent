import { describe, expect, it, vi } from 'vitest';
import { PcmPlayer } from './pcmPlayer';

class FakeSource {
  buffer: { duration: number } | null = null;
  startedAt: number | null = null;
  stopped = false;
  onended: (() => void) | null = null;
  connect() {}
  start(when: number) {
    this.startedAt = when;
  }
  stop() {
    this.stopped = true;
  }
}

class FakeContext {
  static last: FakeContext;
  currentTime = 0;
  destination = {};
  sources: FakeSource[] = [];
  closed = false;

  constructor(readonly options: { sampleRate: number }) {
    FakeContext.last = this;
  }

  createBuffer(_channels: number, length: number, rate: number) {
    return { duration: length / rate, copyToChannel: vi.fn() };
  }

  createBufferSource() {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }

  async close() {
    this.closed = true;
  }
}

function makePlayer() {
  const player = new PcmPlayer(
    1000,
    FakeContext as unknown as new (options?: AudioContextOptions) => AudioContext
  );
  return { player, context: FakeContext.last };
}

const chunk = (samples: number) => new Int16Array(samples).buffer;

describe('PcmPlayer', () => {
  it('creates the context at the requested sample rate', () => {
    const { context } = makePlayer();
    expect(context.options.sampleRate).toBe(1000);
  });

  it('schedules consecutive chunks gaplessly', () => {
    const { player, context } = makePlayer();
    player.enqueue(chunk(100)); // 100 ms
    player.enqueue(chunk(200)); // 200 ms
    const [a, b] = context.sources;
    expect(a.startedAt).toBeCloseTo(0.03, 5);
    expect(b.startedAt).toBeCloseTo(0.13, 5);
  });

  it('ignores empty chunks', () => {
    const { player, context } = makePlayer();
    player.enqueue(new ArrayBuffer(0));
    expect(context.sources).toHaveLength(0);
  });

  it('flush stops every scheduled source and keeps played time', () => {
    const { player, context } = makePlayer();
    player.enqueue(chunk(1000)); // 1 s starting at 0.03
    player.enqueue(chunk(1000));
    context.currentTime = 0.53;
    expect(player.playedMs()).toBe(500);
    player.flush();
    expect(context.sources.every((source) => source.stopped)).toBe(true);
    expect(player.playedMs()).toBe(500);
    player.enqueue(chunk(100));
    expect(context.sources).toHaveLength(3);
  });

  it('caps playedMs at the scheduled duration', () => {
    const { player, context } = makePlayer();
    player.enqueue(chunk(100));
    context.currentTime = 10;
    expect(player.playedMs()).toBe(100);
  });

  it('fires onDrained after the last source ends', () => {
    const { player, context } = makePlayer();
    const drained = vi.fn();
    player.onDrained = drained;
    player.enqueue(chunk(100));
    player.enqueue(chunk(100));
    context.sources[0].onended?.();
    expect(drained).not.toHaveBeenCalled();
    context.sources[1].onended?.();
    expect(drained).toHaveBeenCalledTimes(1);
  });

  it('close flushes and closes the context', async () => {
    const { player, context } = makePlayer();
    player.enqueue(chunk(100));
    await player.close();
    expect(context.sources[0].stopped).toBe(true);
    expect(context.closed).toBe(true);
  });

  it('is audible only once scheduled audio has started, until drained or flushed', () => {
    const { player, context } = makePlayer();
    expect(player.audible()).toBe(false);
    player.enqueue(chunk(500)); // starts at 0.03s
    expect(player.audible()).toBe(false);
    context.currentTime = 0.1;
    expect(player.audible()).toBe(true);
    context.sources[0].onended?.();
    expect(player.audible()).toBe(false);
    player.enqueue(chunk(500));
    context.currentTime = 0.5;
    expect(player.audible()).toBe(true);
    player.flush();
    expect(player.audible()).toBe(false);
  });
});
