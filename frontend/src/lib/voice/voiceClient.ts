import { getApiBase } from '../api';
import { parseVoiceServerMessage, type VoiceServerMessage } from './types';

export interface VoiceClientCallbacks {
  onMessage?: (message: VoiceServerMessage) => void;
  onAudio?: (audio: ArrayBuffer) => void;
  onClose?: (unexpected: boolean) => void;
  onError?: () => void;
}

type WebSocketConstructor = new (url: string) => WebSocket;

export class VoiceClient {
  private socket: WebSocket | null = null;
  private ready = false;
  private stopping = false;

  constructor(
    private readonly callbacks: VoiceClientCallbacks = {},
    private readonly Socket: WebSocketConstructor = WebSocket
  ) {}

  connect(chatId: string | null): void {
    this.stopping = false;
    const url = new URL(getApiBase() || window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/ws/voice';
    url.search = '';
    if (chatId) url.searchParams.set('chat_id', chatId);
    const socket = new this.Socket(url.toString());
    socket.binaryType = 'arraybuffer';
    socket.onmessage = (event: MessageEvent<string | ArrayBuffer | Blob>) => {
      if (event.data instanceof ArrayBuffer) {
        if (this.ready) this.callbacks.onAudio?.(event.data);
        return;
      }
      if (typeof event.data !== 'string') return;
      const message = parseVoiceServerMessage(event.data);
      if (!message) return;
      if (message.type === 'ready') this.ready = true;
      this.callbacks.onMessage?.(message);
    };
    socket.onerror = () => this.callbacks.onError?.();
    socket.onclose = () => {
      const unexpected = !this.stopping;
      this.ready = false;
      this.socket = null;
      this.callbacks.onClose?.(unexpected);
    };
    this.socket = socket;
  }

  sendAudio(audio: Int16Array | ArrayBuffer): boolean {
    if (!this.ready || this.socket?.readyState !== WebSocket.OPEN) return false;
    const buffer = audio instanceof Int16Array ? audio.slice().buffer : audio;
    this.socket.send(buffer);
    return true;
  }

  interrupt(playedMs: number): void {
    this.sendJson({ type: 'interrupt', played_ms: Math.max(0, Math.round(playedMs)) });
  }

  /** Diagnostics for the server log (mic settings, echo gate stats). */
  sendInfo(info: Record<string, string | number | boolean | null>): void {
    this.sendJson({ type: 'client_info', info });
  }

  stop(): void {
    this.stopping = true;
    this.sendJson({ type: 'stop' });
    this.ready = false;
  }

  close(): void {
    this.stopping = true;
    this.ready = false;
    this.socket?.close();
    this.socket = null;
  }

  private sendJson(
    message:
      | { type: 'interrupt'; played_ms: number }
      | { type: 'stop' }
      | { type: 'client_info'; info: Record<string, string | number | boolean | null> }
  ): void {
    if (!this.ready || this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify(message));
  }
}
