import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pollWhileVisible } from './visiblePolling';

class FakeDocument extends EventTarget {
  visibilityState: 'visible' | 'hidden' = 'visible';

  setVisibility(state: 'visible' | 'hidden'): void {
    this.visibilityState = state;
    this.dispatchEvent(new Event('visibilitychange'));
  }
}

describe('pollWhileVisible', () => {
  let fakeDocument: FakeDocument;

  beforeEach(() => {
    vi.useFakeTimers();
    fakeDocument = new FakeDocument();
    vi.stubGlobal('document', fakeDocument);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('polls while the window is visible', () => {
    const refresh = vi.fn();
    const stop = pollWhileVisible(refresh, 1000);
    vi.advanceTimersByTime(3000);
    expect(refresh).toHaveBeenCalledTimes(3);
    stop();
  });

  it('skips ticks while hidden and catches up once shown', () => {
    const refresh = vi.fn();
    const stop = pollWhileVisible(refresh, 1000);

    fakeDocument.setVisibility('hidden');
    vi.advanceTimersByTime(5000);
    expect(refresh).not.toHaveBeenCalled();

    fakeDocument.setVisibility('visible');
    expect(refresh).toHaveBeenCalledTimes(1);
    stop();
  });

  it('stops polling and listening once stopped', () => {
    const refresh = vi.fn();
    const stop = pollWhileVisible(refresh, 1000);
    stop();

    vi.advanceTimersByTime(5000);
    fakeDocument.setVisibility('hidden');
    fakeDocument.setVisibility('visible');
    expect(refresh).not.toHaveBeenCalled();
  });
});
