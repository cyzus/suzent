import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const harness = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  setters: [] as ReturnType<typeof vi.fn>[],
  stateIndex: 0,
  fetch: vi.fn(),
}));

vi.mock('react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react')>()),
  useState: (initial: unknown) => {
    const index = harness.stateIndex++;
    const setter = vi.fn();
    harness.setters[index] = setter;
    return [index === 0 ? 'session-a' : initial, setter];
  },
  useEffect: (effect: () => void | (() => void)) => harness.effects.push(effect),
}));
vi.mock('../../hooks/useChatStore', () => ({
  useChatStore: () => ({ currentChatId: 'session-a', chats: [] }),
}));
vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('../../lib/memoryApi', () => ({
  memoryApi: { getSessionTranscript: harness.fetch },
}));

import { TranscriptPanel } from './TranscriptPanel';

describe('transcript refresh lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    harness.stateIndex = 0;
    harness.effects = [];
    harness.setters = [];
    harness.fetch.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it('refreshes without replacing the content with a loading screen and stops on unmount', async () => {
    harness.fetch.mockResolvedValue({ entries: [{ content: 'updated' }] });
    TranscriptPanel({});
    const cleanup = harness.effects[1]() as () => void;
    await vi.advanceTimersByTimeAsync(0);
    expect(harness.setters[1]).toHaveBeenCalledWith([{ content: 'updated' }]);
    harness.setters[2].mockClear();
    await vi.advanceTimersByTimeAsync(5000);
    expect(harness.fetch).toHaveBeenCalledTimes(2);
    expect(harness.setters[2]).not.toHaveBeenCalledWith(true);
    cleanup();
    await vi.advanceTimersByTimeAsync(10000);
    expect(harness.fetch).toHaveBeenCalledTimes(2);
  });

  it('ignores a pending response after switching sessions', async () => {
    let resolve!: (result: { entries: unknown[] }) => void;
    harness.fetch.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      })
    );
    TranscriptPanel({});
    const cleanup = harness.effects[1]() as () => void;
    cleanup();
    resolve({ entries: [{ content: 'old session' }] });
    await vi.advanceTimersByTimeAsync(10000);
    expect(harness.setters[1]).not.toHaveBeenCalled();
    expect(harness.fetch).toHaveBeenCalledTimes(1);
  });
});
