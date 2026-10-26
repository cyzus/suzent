import { afterEach, describe, expect, it, vi } from 'vitest';

const fetchStatus = vi.hoisted(() => vi.fn());
const busListeners = vi.hoisted(() => new Set<(payload: unknown) => void>());

vi.mock('../lib/focalAgent', () => ({ fetchFocalAgentStatus: fetchStatus }));
vi.mock('./useEventBus', () => ({
  subscribeToBusPayloads: (listener: (payload: unknown) => void) => {
    busListeners.add(listener);
    return () => busListeners.delete(listener);
  },
}));

import { refreshFocalStatus, subscribeToFocalStatus } from './useFocalStatus';

describe('subscribeToFocalStatus', () => {
  afterEach(() => {
    vi.useRealTimers();
    fetchStatus.mockReset();
    busListeners.clear();
  });

  it('runs one poll for every component showing Regent, and stops with the last', async () => {
    vi.useFakeTimers();
    fetchStatus.mockResolvedValue({ chatId: 'focal-suzent', waiting: 0 });
    const card = vi.fn();
    const header = vi.fn();

    const leaveCard = subscribeToFocalStatus(card);
    const leaveHeader = subscribeToFocalStatus(header);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(fetchStatus).toHaveBeenCalledTimes(2);
    expect(busListeners.size).toBe(1);
    expect(card).toHaveBeenCalled();
    expect(header).toHaveBeenCalled();

    leaveCard();
    leaveHeader();
    fetchStatus.mockClear();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchStatus).not.toHaveBeenCalled();
    expect(busListeners.size).toBe(0);
  });

  it('pushes a fresh status to subscribers on demand, between polls', async () => {
    vi.useFakeTimers();
    fetchStatus.mockResolvedValue({ chatId: 'focal-suzent', unread: 1 });
    const card = vi.fn();
    const leave = subscribeToFocalStatus(card);
    await vi.advanceTimersByTimeAsync(0);
    card.mockClear();

    fetchStatus.mockResolvedValue({ chatId: 'focal-suzent', unread: 0 });
    await refreshFocalStatus();

    expect(card).toHaveBeenCalledTimes(1);
    leave();
  });
});
