import { getApiBase } from '../api';
import { withAuthQuery } from '../authToken';
import { float32ToInt16, StreamingLinearResampler } from './pcm';

/** Why the wake word is not listening, as the server names it. */
export type WakeErrorCode =
  'not_installed' | 'no_model' | 'no_keywords' | 'unknown_words' | 'mic' | 'connection';

export interface WakeListenerCallbacks {
  onListening?: () => void;
  onWake?: (phrase: string) => void;
  onError?: (code: WakeErrorCode, detail: string) => void;
}

/** A running microphone capture; `close` releases the device. */
export interface MicCapture {
  close: () => Promise<void>;
}

export type OpenMic = (sampleRate: number, onPcm: (pcm: Int16Array) => void) => Promise<MicCapture>;

type WebSocketConstructor = new (url: string) => WebSocket;

/** Capture the default mic as 16-bit mono PCM at `sampleRate`, in ~30 ms frames. */
export const openMic: OpenMic = async (sampleRate, onPcm) => {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  const context = new AudioContext();
  const release = async () => {
    stream.getTracks().forEach((track) => track.stop());
    if (context.state !== 'closed') await context.close();
  };
  try {
    await context.audioWorklet.addModule(
      new URL('voice-capture-worklet.js', document.baseURI).href
    );
    const source = context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(context, 'voice-capture');
    const resampler = new StreamingLinearResampler(context.sampleRate, sampleRate);
    worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      const samples = resampler.process(new Float32Array(event.data));
      if (samples.length) onPcm(float32ToInt16(samples));
    };
    source.connect(worklet);
    worklet.connect(context.destination);
    await context.resume();
    return {
      close: async () => {
        worklet.port.onmessage = null;
        worklet.disconnect();
        await release();
      },
    };
  } catch (error) {
    await release();
    throw error;
  }
};

/**
 * Listens for the wake phrase: streams the mic to `/ws/wake`, where the
 * spotter runs on this machine, and reports each phrase it hears. The mic is
 * opened only once the server says it can listen, and released on `stop`.
 */
export class WakeListener {
  private socket: WebSocket | null = null;
  private mic: MicCapture | null = null;
  private stopped = false;

  constructor(
    private readonly callbacks: WakeListenerCallbacks = {},
    private readonly open: OpenMic = openMic,
    private readonly Socket: WebSocketConstructor = WebSocket
  ) {}

  start(): void {
    const url = new URL(getApiBase() || window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/ws/wake';
    url.search = '';
    const socket = new this.Socket(withAuthQuery(url.toString()));
    this.socket = socket;
    let failed = false;
    const fail = (code: WakeErrorCode, detail = '') => {
      if (this.stopped || failed) return;
      failed = true;
      this.stop();
      this.callbacks.onError?.(code, detail);
    };
    socket.onmessage = (event: MessageEvent<unknown>) => {
      if (typeof event.data !== 'string') return;
      let message: {
        type?: string;
        sample_rate?: number;
        phrase?: string;
        code?: string;
        detail?: string;
      };
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === 'ready') {
        this.open(message.sample_rate ?? 16000, (pcm) => {
          // 1: OPEN. Frames captured while the line closes are dropped.
          if (socket.readyState === 1) socket.send(pcm.buffer);
        }).then(
          (mic) => {
            if (this.stopped) void mic.close();
            else {
              this.mic = mic;
              this.callbacks.onListening?.();
            }
          },
          () => fail('mic')
        );
      } else if (message.type === 'wake') {
        this.callbacks.onWake?.(message.phrase ?? '');
      } else if (message.type === 'error') {
        fail((message.code as WakeErrorCode) ?? 'connection', message.detail ?? '');
      }
    };
    socket.onerror = () => fail('connection');
    socket.onclose = () => fail('connection');
  }

  stop(): void {
    this.stopped = true;
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.close();
    }
    const mic = this.mic;
    this.mic = null;
    void mic?.close();
  }
}
