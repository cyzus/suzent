import { afterEach, describe, expect, it, vi } from 'vitest';
import { connectBrowserPreview } from './browserPreview';

describe('preview connection lifetime', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function setup() {
    vi.useFakeTimers();
    const sockets: Array<{ onclose: (() => void) | null; close: ReturnType<typeof vi.fn> }> = [];
    vi.stubGlobal(
      'WebSocket',
      class {
        onclose: (() => void) | null = null;
        close = vi.fn(() => this.onclose?.());
        constructor() {
          sockets.push(this);
        }
      }
    );
    const status = vi.fn();
    const cleanup = connectBrowserPreview('ws://localhost/ws/browser', vi.fn(), status, vi.fn());
    return { sockets, status, cleanup };
  }

  it('does not reconnect after a visible connection is disposed', () => {
    const { sockets, cleanup } = setup();
    cleanup();
    vi.advanceTimersByTime(10000);
    expect(sockets).toHaveLength(1);
    expect(sockets[0].close).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('cancels an already scheduled reconnect when hidden or unmounted', () => {
    const { sockets, cleanup } = setup();
    sockets[0].onclose?.();
    cleanup();
    vi.advanceTimersByTime(10000);
    expect(sockets).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('reconnects after a network interruption while still visible', () => {
    const { sockets, cleanup, status } = setup();
    sockets[0].onclose?.();
    expect(status).toHaveBeenLastCalledWith('disconnected');
    vi.advanceTimersByTime(3000);
    expect(sockets).toHaveLength(2);
    cleanup();
    expect(sockets[1].close).toHaveBeenCalledOnce();
  });
});
