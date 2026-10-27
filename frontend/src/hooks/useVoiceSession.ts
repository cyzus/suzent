import { useCallback, useEffect, useReducer, useRef } from 'react';
import { EchoGate, frameDb } from '../lib/voice/echoGate';
import { float32ToInt16, StreamingLinearResampler } from '../lib/voice/pcm';
import { PcmPlayer } from '../lib/voice/pcmPlayer';
import type { VoiceServerMessage, VoiceServerState } from '../lib/voice/types';
import { VoiceClient } from '../lib/voice/voiceClient';

export type VoiceSessionStatus = 'idle' | 'connecting' | VoiceServerState | 'error';
export interface VoiceTranscript {
  id: string;
  speaker: 'user' | 'assistant';
  text: string;
  final: boolean;
}
export interface VoiceSessionState {
  status: VoiceSessionStatus;
  /** This call's lines, live and final. The chat window holds the conversation. */
  transcripts: VoiceTranscript[];
  /** Suzent (the main agent) is working on a delegated task. */
  working: boolean;
  /** Whether the model streams the user's words while they speak (null: unknown). */
  liveCaptions: boolean | null;
  errorKey: string | null;
  /** Suzent's reply audio is queued or playing locally. */
  playing: boolean;
}
export type VoiceSessionAction =
  | { type: 'start' }
  | { type: 'ready'; liveCaptions: boolean | null; working: boolean }
  | { type: 'state'; state: VoiceServerState }
  | { type: 'working'; active: boolean }
  | { type: 'transcript'; transcript: VoiceTranscript }
  | { type: 'interrupted' }
  | { type: 'playback'; playing: boolean }
  | { type: 'error'; key: string }
  | { type: 'closed' }
  | { type: 'stop' };

export const initialVoiceSessionState: VoiceSessionState = {
  status: 'idle',
  transcripts: [],
  working: false,
  liveCaptions: null,
  errorKey: null,
  playing: false,
};

// Captions only need the latest exchange; the bar never shows more.
const MAX_LINES = 20;

export function voiceSessionReducer(
  state: VoiceSessionState,
  action: VoiceSessionAction
): VoiceSessionState {
  switch (action.type) {
    case 'start':
      return { ...initialVoiceSessionState, status: 'connecting' };
    case 'stop':
      return initialVoiceSessionState;
    case 'closed':
      // The server ended the call; keep an error on screen until dismissed.
      return state.status === 'error' ? state : initialVoiceSessionState;
    case 'ready':
      return { ...state, liveCaptions: action.liveCaptions, working: action.working };
    case 'state':
      // A late state from the server must not revive an ended or failed call.
      if (state.status === 'idle' || state.status === 'error') return state;
      return { ...state, status: action.state };
    case 'working':
      return { ...state, working: action.active };
    case 'playback':
      return state.playing === action.playing ? state : { ...state, playing: action.playing };
    case 'error':
      return { ...state, status: 'error', errorKey: action.key, working: false };
    case 'interrupted':
      // The cut-off reply gets no end-of-part event: settle its caption.
      if (!state.transcripts.some((line) => line.speaker === 'assistant' && !line.final))
        return state;
      return {
        ...state,
        transcripts: state.transcripts.map((line) =>
          line.speaker === 'assistant' && !line.final ? { ...line, final: true } : line
        ),
      };
    case 'transcript': {
      const incoming = action.transcript;
      const index = state.transcripts.findIndex((item) => item.id === incoming.id);
      const transcripts = [...state.transcripts];
      if (index >= 0) {
        // A finalized line never reverts to a live one.
        if (transcripts[index].final && !incoming.final) return state;
        transcripts[index] = incoming;
      } else transcripts.push(incoming);
      return { ...state, transcripts: transcripts.slice(-MAX_LINES) };
    }
  }
}

/**
 * The status to show. The server says `listening` once the provider has sent
 * the whole reply, but a provider that streams faster than real time (Qwen-Omni
 * sends ~6x) leaves seconds of it still playing here: that is still speaking.
 */
export function shownStatus(state: VoiceSessionState): VoiceSessionStatus {
  return state.status === 'listening' && state.playing ? 'speaking' : state.status;
}

/** The newest line from each speaker: what the caption strip shows. */
export function latestLines(transcripts: VoiceTranscript[]): {
  user: VoiceTranscript | null;
  assistant: VoiceTranscript | null;
} {
  let user: VoiceTranscript | null = null;
  let assistant: VoiceTranscript | null = null;
  for (let i = transcripts.length - 1; i >= 0 && !(user && assistant); i -= 1) {
    const line = transcripts[i];
    if (line.speaker === 'user') user ??= line;
    else assistant ??= line;
  }
  return { user, assistant };
}

const ERROR_KEYS = new Set([
  'no_model',
  'no_api_key',
  'unsupported_provider',
  'session_error',
  'busy',
]);
const errorKey = (code: string) => `voice.errors.${ERROR_KEYS.has(code) ? code : 'session_error'}`;

/** Loudness of one mic frame on a 0..1 scale: RMS mapped through -60..-10 dBFS. */
export function frameLevel(frame: Float32Array): number {
  return Math.min(1, Math.max(0, (frameDb(frame) + 60) / 50));
}

/** Send how the echo gate did this call (once), for the server log. */
function reportEchoGate(gateRef: { current: EchoGate | null }, client: VoiceClient | null): void {
  const gate = gateRef.current;
  gateRef.current = null;
  if (!gate) return;
  // Dropped silently if the line is already gone.
  client?.sendInfo({
    event: 'echo_gate',
    ...gate.stats,
    threshold_db: Math.round(gate.threshold()),
  });
}

export function voiceSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    typeof window !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    'AudioContext' in window &&
    'AudioWorkletNode' in window
  );
}

/** `onChatBound` runs once the server has bound the call to a chat (new or existing). */
export function useVoiceSession(onChatBound: (chatId: string) => void) {
  const [state, dispatch] = useReducer(voiceSessionReducer, initialVoiceSessionState);
  const clientRef = useRef<VoiceClient | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inputContextRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const playerRef = useRef<PcmPlayer | null>(null);
  // Input loudness 0..1, written per 30ms mic frame. A ref, not state: the
  // meter reads it every animation frame without re-rendering the chat.
  const micLevelRef = useRef(0);
  const gateRef = useRef<EchoGate | null>(null);
  const onChatBoundRef = useRef(onChatBound);
  onChatBoundRef.current = onChatBound;
  // Bumped by every cleanup, so a capture still awaiting the mic permission
  // prompt can tell its call has ended and release what it opened.
  const generationRef = useRef(0);

  const cleanup = useCallback(async () => {
    generationRef.current += 1;
    // Detach everything synchronously, before the first await: a start() that
    // runs during the awaits below installs a new call, which this must not touch.
    const worklet = workletRef.current;
    const stream = streamRef.current;
    const input = inputContextRef.current;
    const player = playerRef.current;
    const client = clientRef.current;
    workletRef.current = null;
    streamRef.current = null;
    inputContextRef.current = null;
    playerRef.current = null;
    clientRef.current = null;
    micLevelRef.current = 0;
    reportEchoGate(gateRef, client);
    client?.close();
    worklet?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());
    if (input && input.state !== 'closed') await input.close();
    if (player) await player.close();
  }, []);

  const startCapture = useCallback(async (sampleRate: number) => {
    if (!voiceSupported()) throw new Error('unsupported');
    const generation = generationRef.current;
    const cancelled = () => generation !== generationRef.current;
    const client = clientRef.current;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (cancelled()) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    streamRef.current = stream;
    // What the browser actually granted: if echoCancellation is false here,
    // Suzent's voice reaches the provider unfiltered (the echo gate is all
    // that stands in the way). Logged server-side for diagnosis.
    const track = stream.getAudioTracks()[0];
    const granted = track?.getSettings?.() ?? {};
    client?.sendInfo({
      event: 'mic',
      echo_cancellation: granted.echoCancellation ?? null,
      noise_suppression: granted.noiseSuppression ?? null,
      auto_gain_control: granted.autoGainControl ?? null,
      sample_rate: granted.sampleRate ?? null,
      device: track?.label ?? '',
    });
    const context = new AudioContext();
    inputContextRef.current = context;
    await context.audioWorklet.addModule(
      new URL('voice-capture-worklet.js', document.baseURI).href
    );
    // cleanup() already released the stream and context it found in the refs.
    if (cancelled()) return;
    const source = context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(context, 'voice-capture');
    workletRef.current = worklet;
    const resampler = new StreamingLinearResampler(context.sampleRate, sampleRate);
    const gate = new EchoGate();
    gateRef.current = gate;
    worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      // Frames still queued from an ended call must not reach the next one.
      if (cancelled()) return;
      const frame = new Float32Array(event.data);
      // The meter shows what the mic hears, gated or not.
      micLevelRef.current = frameLevel(frame);
      const frameMs = (frame.length / context.sampleRate) * 1000;
      const audible = playerRef.current?.audible() ?? false;
      for (const out of gate.process(frame, frameMs, audible, performance.now())) {
        const samples = resampler.process(out);
        if (samples.length) client?.sendAudio(float32ToInt16(samples));
      }
    };
    source.connect(worklet);
    worklet.connect(context.destination);
    await context.resume();
  }, []);

  const handleMessage = useCallback(
    (message: VoiceServerMessage) => {
      if (message.type === 'ready') {
        const player = new PcmPlayer(message.output_sample_rate);
        player.onPlayingChange = (playing) => {
          // close() of an ended call flushes; that must not reach the next call.
          if (playerRef.current === player) dispatch({ type: 'playback', playing });
        };
        playerRef.current = player;
        dispatch({
          type: 'ready',
          liveCaptions: message.live_captions ?? null,
          working: !!message.working,
        });
        onChatBoundRef.current(message.chat_id);
        const generation = generationRef.current;
        void startCapture(message.input_sample_rate).catch((error: unknown) => {
          // A mic failure from an ended call must not end the one that replaced it.
          if (generation !== generationRef.current) return;
          const denied = error instanceof DOMException && error.name === 'NotAllowedError';
          dispatch({
            type: 'error',
            key: denied ? 'voice.errors.micDenied' : 'voice.errors.micUnavailable',
          });
          void cleanup();
        });
      } else if (message.type === 'state') dispatch({ type: 'state', state: message.state });
      else if (message.type === 'transcript') {
        dispatch({
          type: 'transcript',
          transcript: {
            id: message.id,
            speaker: message.speaker,
            text: message.text,
            final: message.final,
          },
        });
      } else if (message.type === 'working') dispatch({ type: 'working', active: message.active });
      else if (message.type === 'interrupted') {
        playerRef.current?.flush();
        dispatch({ type: 'interrupted' });
      } else if (message.type === 'error') dispatch({ type: 'error', key: errorKey(message.code) });
      else if (message.type === 'closed') {
        void cleanup();
        dispatch({ type: 'closed' });
      }
    },
    [cleanup, startCapture]
  );

  const start = useCallback(
    (chatId: string | null) => {
      if (!voiceSupported()) {
        dispatch({ type: 'error', key: 'voice.errors.micUnavailable' });
        return;
      }
      // cleanup() detaches the old call synchronously; its audio teardown can
      // finish in the background. Starting at once (not after it) means two
      // quick starts can never leave two live clients.
      void cleanup();
      dispatch({ type: 'start' });
      // A stale client from an earlier call must not touch this one.
      const current = () => clientRef.current === client;
      const client: VoiceClient = new VoiceClient({
        onMessage: (message) => {
          if (current()) handleMessage(message);
        },
        onAudio: (audio) => {
          if (current()) playerRef.current?.enqueue(audio);
        },
        onError: () => {
          if (current()) dispatch({ type: 'error', key: 'voice.errors.session_error' });
        },
        onClose: (unexpected) => {
          if (!unexpected || !current()) return;
          // The line dropped: release the mic now, keep the error on screen.
          dispatch({ type: 'error', key: 'voice.errors.session_error' });
          void cleanup();
        },
      });
      clientRef.current = client;
      client.connect(chatId);
    },
    [cleanup, handleMessage]
  );

  const interrupt = useCallback(() => {
    const played = playerRef.current?.playedMs() ?? 0;
    clientRef.current?.interrupt(played);
    playerRef.current?.flush();
  }, []);

  const stop = useCallback(() => {
    reportEchoGate(gateRef, clientRef.current);
    clientRef.current?.stop();
    void cleanup();
    dispatch({ type: 'stop' });
  }, [cleanup]);

  useEffect(() => () => void cleanup(), [cleanup]);
  return {
    ...state,
    status: shownStatus(state),
    micLevel: micLevelRef as { readonly current: number },
    active: state.status !== 'idle' && state.status !== 'error',
    supported: voiceSupported(),
    start,
    stop,
    interrupt,
  };
}

export type VoiceSession = ReturnType<typeof useVoiceSession>;
