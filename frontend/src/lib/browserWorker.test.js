import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

it.each(['evaluate', 'attach'])(
  'disconnect bypasses a stalled %s and reconnect starts a fresh queue',
  async (stalled) => {
    let release;
    const pending = new Promise((resolve) => {
      release = resolve;
    });
    const event = () => ({ addListener: vi.fn() });
    const api = {
      debugger: {
        attach: vi.fn(() => (stalled === 'attach' ? pending : Promise.resolve())),
        detach: vi.fn(async () => {}),
        sendCommand: vi.fn(async (_, method) => (method === 'Runtime.evaluate' ? pending : {})),
        onEvent: event(),
        onDetach: event(),
      },
      tabs: {
        get: vi.fn(async () => ({ url: 'https://example.com', title: 'Example' })),
        query: vi.fn(async () => []),
      },
      runtime: {
        onMessage: event(),
        onStartup: event(),
        sendNativeMessage: vi.fn(async () => ({ url: 'ws://127.0.0.1:8000/ws/browser-extension' })),
      },
      storage: {
        local: {
          get: vi.fn(async () => ({
            pairing: { url: 'ws://127.0.0.1:8000/ws/browser-extension', token: 'token' },
          })),
        },
      },
      action: { setBadgeText: vi.fn() },
      alarms: { create: vi.fn(), onAlarm: event() },
    };
    const sockets = [];
    class Socket {
      static OPEN = 1;
      static CONNECTING = 0;
      readyState = 1;
      sent = [];
      constructor() {
        sockets.push(this);
      }
      send(data) {
        this.sent.push(JSON.parse(data));
      }
      close() {
        this.readyState = 3;
        this.onclose?.({ code: 1011 });
      }
      command(id, action, params = {}) {
        this.onmessage({ data: JSON.stringify({ id, action, params }) });
      }
    }
    vi.stubGlobal('chrome', api);
    vi.stubGlobal('WebSocket', Socket);
    vi.stubGlobal('navigator', { userAgent: 'Edg/123' });
    await import('../../../extensions/browser/worker.js');
    await vi.waitFor(() => expect(sockets).toHaveLength(1));
    const original = sockets[0];
    original.command(1, 'select', { id: 'tab-1' });
    await vi.waitFor(() => expect(api.debugger.attach).toHaveBeenCalled());
    if (stalled === 'evaluate') {
      await vi.waitFor(() => expect(original.sent.some((message) => message.id === 1)).toBe(true));
      original.command(2, 'cdp', { method: 'Runtime.evaluate' });
      await vi.waitFor(() =>
        expect(api.debugger.sendCommand).toHaveBeenCalledWith({ tabId: 1 }, 'Runtime.evaluate', {})
      );
    }
    original.close();
    await vi.waitFor(() => expect(api.debugger.detach).toHaveBeenCalledWith({ tabId: 1 }));
    api.alarms.onAlarm.addListener.mock.calls[0][0]();
    await vi.waitFor(() => expect(sockets).toHaveLength(2));
    sockets[1].command(3, 'tabs');
    await vi.waitFor(() => expect(sockets[1].sent.some((message) => message.id === 3)).toBe(true));
    release({});
    sockets[1].command(4, 'status');
    await vi.waitFor(() => expect(sockets[1].sent.some((message) => message.id === 4)).toBe(true));
    expect(sockets[1].sent.find((message) => message.id === 4).result.selected).toBe(false);
    expect(sockets[1].sent.some((message) => message.id === 1 || message.id === 2)).toBe(false);
    sockets[1].close();
  }
);
