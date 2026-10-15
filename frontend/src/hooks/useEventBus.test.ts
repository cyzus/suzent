import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('react', () => ({ useEffect: vi.fn(), useState: () => [0, vi.fn()] }));
vi.mock('../lib/api', () => ({ getApiBase: () => 'http://localhost' }));
vi.mock('../lib/authToken', () => ({ withAuthQuery: (url: string) => url }));

import { subscribeToBusPayloads, useEventBus } from './useEventBus';

class FakeEventSource {
  static current: FakeEventSource;
  onmessage?: (event: MessageEvent) => void;
  onerror?: () => void;
  constructor() {
    FakeEventSource.current = this;
  }
  close(): void {}
  send(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

afterEach(() => vi.unstubAllGlobals());

describe('memory background status', () => {
  it('restores snapshots and remains independent of reply completion', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    const unsubscribe = subscribeToBusPayloads(() => {});
    try {
      const source = FakeEventSource.current;
      source.send({ event: 'snapshot', streams: ['chat'], memory_chats: ['chat'] });
      expect(useEventBus().memoryChats.has('chat')).toBe(true);
      source.send({ event: 'stream_ended', chat_id: 'chat' });
      expect(useEventBus().isStreaming('chat')).toBe(false);
      expect(useEventBus().memoryChats.has('chat')).toBe(true);
      source.send({ event: 'memory_processing', chat_id: 'chat', active: false });
      expect(useEventBus().memoryChats.has('chat')).toBe(false);
      source.send({ event: 'memory_processing', chat_id: 'other', active: true });
      expect(useEventBus().memoryChats.has('other')).toBe(true);
      source.send({ event: 'snapshot', streams: [], memory_chats: [] });
      expect(useEventBus().memoryChats.size).toBe(0);
    } finally {
      unsubscribe();
    }
  });
});
