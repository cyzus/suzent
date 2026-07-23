import { afterEach, describe, expect, it, vi } from 'vitest';

import { closeImmediatelyAndPersist } from './settingsPersistence';

describe('closeImmediatelyAndPersist', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('closes synchronously and defers persistence', async () => {
    vi.useFakeTimers();
    const events: string[] = [];

    closeImmediatelyAndPersist(
      () => events.push('closed'),
      async () => {
        events.push('persisted');
      },
      () => events.push('failed'),
    );

    expect(events).toEqual(['closed']);

    await vi.runAllTimersAsync();

    expect(events).toEqual(['closed', 'persisted']);
  });

  it('reports background persistence failures without delaying close', async () => {
    vi.useFakeTimers();
    const onError = vi.fn();

    closeImmediatelyAndPersist(
      vi.fn(),
      async () => {
        throw new Error('save failed');
      },
      onError,
    );

    await vi.runAllTimersAsync();

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'save failed' }));
  });
});
