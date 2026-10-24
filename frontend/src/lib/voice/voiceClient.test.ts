import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VoiceClient } from './voiceClient';
import type { VoiceServerMessage } from './types';

vi.mock('../api', () => ({ getApiBase: () => 'http://127.0.0.1:8000' }));

class FakeSocket {
  static instances: FakeSocket[] = [];
  static OPEN = 1;
  url: string;
  binaryType = 'blob';
  readyState = 1;
  sent: Array<string | ArrayBuffer> = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }

  emit(data: string | ArrayBuffer) {
    this.onmessage?.({ data } as MessageEvent);
  }
}

const READY = JSON.stringify({
  type: 'ready',
  chat_id: 'c1',
  input_sample_rate: 24000,
  output_sample_rate: 24000,
  model: 'openai/gpt-realtime',
});

function setup() {
  const messages: VoiceServerMessage[] = [];
  const audio: ArrayBuffer[] = [];
  const closes: boolean[] = [];
  const client = new VoiceClient(
    {
      onMessage: (message) => messages.push(message),
      onAudio: (chunk) => audio.push(chunk),
      onClose: (unexpected) => closes.push(unexpected),
    },
    FakeSocket as unknown as new (url: string) => WebSocket
  );
  return { client, messages, audio, closes };
}

describe('VoiceClient', () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeSocket);
  });

  it('connects to /ws/voice with chat_id and arraybuffer frames', () => {
    const { client } = setup();
    client.connect('abc');
    const socket = FakeSocket.instances[0];
    const url = new URL(socket.url);
    expect(url.protocol).toBe('ws:');
    expect(url.pathname).toBe('/ws/voice');
    expect(url.searchParams.get('chat_id')).toBe('abc');
    expect(socket.binaryType).toBe('arraybuffer');
  });

  it('omits chat_id when none is given', () => {
    const { client } = setup();
    client.connect(null);
    expect(new URL(FakeSocket.instances[0].url).searchParams.has('chat_id')).toBe(false);
  });

  it('sends nothing before ready', () => {
    const { client } = setup();
    client.connect(null);
    const socket = FakeSocket.instances[0];
    expect(client.sendAudio(new Int16Array([1, 2]))).toBe(false);
    client.interrupt(10);
    expect(socket.sent).toHaveLength(0);
    socket.emit(READY);
    expect(client.sendAudio(new Int16Array([1, 2]))).toBe(true);
    expect(socket.sent).toHaveLength(1);
  });

  it('sends client diagnostics as a client_info control message', () => {
    const { client } = setup();
    client.connect(null);
    const socket = FakeSocket.instances[0];
    client.sendInfo({ event: 'mic', echo_cancellation: false });
    expect(socket.sent).toHaveLength(0); // not before ready
    socket.emit(READY);
    client.sendInfo({ event: 'mic', echo_cancellation: false });
    expect(JSON.parse(socket.sent[0] as string)).toEqual({
      type: 'client_info',
      info: { event: 'mic', echo_cancellation: false },
    });
  });

  it('routes JSON to onMessage and binary to onAudio (only after ready)', () => {
    const { client, messages, audio } = setup();
    client.connect(null);
    const socket = FakeSocket.instances[0];
    socket.emit(new Int16Array([1, 2, 3]).buffer);
    expect(audio).toHaveLength(0);
    socket.emit(READY);
    socket.emit(new Int16Array([1, 2, 3]).buffer);
    socket.emit(JSON.stringify({ type: 'state', state: 'speaking' }));
    socket.emit('not json');
    expect(audio).toHaveLength(1);
    expect(messages.map((message) => message.type)).toEqual(['ready', 'state']);
  });

  it('sends interrupt and stop control messages', () => {
    const { client } = setup();
    client.connect(null);
    const socket = FakeSocket.instances[0];
    socket.emit(READY);
    client.interrupt(123.7);
    expect(JSON.parse(socket.sent[0] as string)).toEqual({ type: 'interrupt', played_ms: 124 });
    client.stop();
    expect(JSON.parse(socket.sent[1] as string)).toEqual({ type: 'stop' });
  });

  it('reports unexpected vs requested close', () => {
    const first = setup();
    first.client.connect(null);
    FakeSocket.instances[0].close();
    expect(first.closes).toEqual([true]);

    const second = setup();
    second.client.connect(null);
    FakeSocket.instances[1].emit(READY);
    second.client.stop();
    FakeSocket.instances[1].close();
    expect(second.closes).toEqual([false]);
  });
});
