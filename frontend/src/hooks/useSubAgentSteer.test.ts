import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearSentSteers,
  getSentSteers,
  markSteerAbsorbed,
  sendSubAgentSteer,
} from './useSubAgentSteer';

// getApiBase reads window to find the Tauri-injected port; browser mode just
// wants relative URLs, which is what an empty __TAURI__ gives us here.
function mockFetch(response: { ok: boolean; body?: unknown }) {
  vi.stubGlobal('window', {});
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: response.ok, json: async () => response.body }))
  );
}

describe('sendSubAgentSteer', () => {
  beforeEach(() => {
    clearSentSteers('t1');
    clearSentSteers('t2');
    vi.unstubAllGlobals();
  });

  it('records a sent redirect as not yet picked up', async () => {
    mockFetch({ ok: true, body: { enqueue_id: 'enq-1' } });

    expect(await sendSubAgentSteer('t1', 'wrap up')).toBe(true);
    expect(getSentSteers('t1')).toEqual([{ enqueueId: 'enq-1', text: 'wrap up', absorbed: false }]);
  });

  it('reports failure when the sub-agent has no live run', async () => {
    mockFetch({ ok: false });

    expect(await sendSubAgentSteer('t1', 'wrap up')).toBe(false);
    expect(getSentSteers('t1')).toEqual([]);
  });

  it('reports failure when the run accepted nothing to track', async () => {
    mockFetch({ ok: true, body: {} });

    expect(await sendSubAgentSteer('t1', 'wrap up')).toBe(false);
    expect(getSentSteers('t1')).toEqual([]);
  });
});

describe('markSteerAbsorbed', () => {
  beforeEach(() => {
    clearSentSteers('t1');
    clearSentSteers('t2');
    mockFetch({ ok: true, body: { enqueue_id: 'enq-1' } });
  });

  it('flips the matching redirect to picked up', async () => {
    await sendSubAgentSteer('t1', 'wrap up');

    markSteerAbsorbed('enq-1');

    expect(getSentSteers('t1')[0].absorbed).toBe(true);
  });

  it('leaves other redirects alone', async () => {
    await sendSubAgentSteer('t1', 'wrap up');

    markSteerAbsorbed('enq-somebody-else');

    expect(getSentSteers('t1')[0].absorbed).toBe(false);
  });

  it('survives an id it has never seen', () => {
    expect(() => markSteerAbsorbed('enq-unknown')).not.toThrow();
  });
});

describe('the record itself', () => {
  beforeEach(() => {
    clearSentSteers('t1');
    clearSentSteers('t2');
  });

  it('keeps each sub-agent separate', async () => {
    mockFetch({ ok: true, body: { enqueue_id: 'enq-a' } });
    await sendSubAgentSteer('t1', 'for one');
    mockFetch({ ok: true, body: { enqueue_id: 'enq-b' } });
    await sendSubAgentSteer('t2', 'for the other');

    expect(getSentSteers('t1').map((s) => s.text)).toEqual(['for one']);
    expect(getSentSteers('t2').map((s) => s.text)).toEqual(['for the other']);
  });

  it('is bounded so a long run cannot grow it without limit', async () => {
    for (let i = 0; i < 14; i++) {
      mockFetch({ ok: true, body: { enqueue_id: `enq-${i}` } });
      await sendSubAgentSteer('t1', `redirect ${i}`);
    }

    const kept = getSentSteers('t1');
    expect(kept).toHaveLength(10);
    expect(kept[kept.length - 1].text).toBe('redirect 13');
  });

  it('reads empty for a sub-agent nothing was sent to', () => {
    expect(getSentSteers('never')).toEqual([]);
    expect(getSentSteers(undefined)).toEqual([]);
  });
});
