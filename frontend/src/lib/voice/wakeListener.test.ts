import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WakeListener, type OpenMic, type WakeErrorCode } from './wakeListener';

vi.mock('../api', () => ({ getApiBase: () => 'http://127.0.0.1:8000' }));

class FakeSocket {
  static instances: FakeSocket[] = [];
  url: string;
  readyState = 1;
  sent: ArrayBuffer[] = [];
  closed = false;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  send(data: ArrayBuffer) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.onclose?.();
  }

  emit(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  }
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function setup(open?: OpenMic) {
  const events: string[] = [];
  const errors: Array<[WakeErrorCode, string]> = [];
  let feed: ((pcm: Int16Array) => void) | null = null;
  const micClose = vi.fn(async () => {});
  const opened: number[] = [];
  const listener = new WakeListener(
    {
      onListening: () => events.push('listening'),
      onWake: (phrase) => events.push(`wake:${phrase}`),
      onError: (code, detail) => errors.push([code, detail]),
    },
    open ??
      (async (rate, onPcm) => {
        opened.push(rate);
        feed = onPcm;
        return { close: micClose };
      }),
    FakeSocket as unknown as new (url: string) => WebSocket
  );
  listener.start();
  return {
    listener,
    events,
    errors,
    micClose,
    opened,
    feed: () => feed,
    socket: FakeSocket.instances.at(-1)!,
  };
}

describe('WakeListener', () => {
  beforeEach(() => {
    FakeSocket.instances = [];
  });

  it('opens the mic only once the server can listen, and streams PCM', async () => {
    const { socket, events, opened, feed } = setup();
    expect(new URL(socket.url).pathname).toBe('/ws/wake');
    expect(opened).toEqual([]);
    socket.emit({ type: 'ready', sample_rate: 16000 });
    await flush();
    expect(opened).toEqual([16000]);
    expect(events).toEqual(['listening']);
    feed()!(new Int16Array([1, 2, 3]));
    expect(socket.sent).toHaveLength(1);
    socket.emit({ type: 'wake', phrase: '你好 Suzent' });
    expect(events).toEqual(['listening', 'wake:你好 Suzent']);
  });

  it('reports why the server cannot listen, without opening the mic', async () => {
    const { socket, errors, opened } = setup();
    socket.emit({ type: 'error', code: 'unknown_words', detail: 'Zorblax' });
    await flush();
    expect(errors).toEqual([['unknown_words', 'Zorblax']]);
    expect(opened).toEqual([]);
    expect(socket.closed).toBe(true);
  });

  it('releases the mic on stop and reports nothing afterwards', async () => {
    const { listener, socket, micClose, errors } = setup();
    socket.emit({ type: 'ready', sample_rate: 16000 });
    await flush();
    listener.stop();
    expect(micClose).toHaveBeenCalledOnce();
    expect(socket.closed).toBe(true);
    expect(errors).toEqual([]);
  });

  it('closes a mic that opens after stop', async () => {
    let resolve: (mic: { close: () => Promise<void> }) => void = () => {};
    const close = vi.fn(async () => {});
    const { listener, socket, events } = setup(() => new Promise((done) => (resolve = done)));
    socket.emit({ type: 'ready', sample_rate: 16000 });
    listener.stop();
    resolve({ close });
    await flush();
    expect(close).toHaveBeenCalledOnce();
    expect(events).toEqual([]);
  });

  it('says so when the mic cannot be opened', async () => {
    const { socket, errors } = setup(() => Promise.reject(new Error('denied')));
    socket.emit({ type: 'ready', sample_rate: 16000 });
    await flush();
    expect(errors).toEqual([['mic', '']]);
  });

  it('treats a dropped line as a connection error', () => {
    const { socket, errors } = setup();
    socket.onclose?.();
    expect(errors).toEqual([['connection', '']]);
  });
});
