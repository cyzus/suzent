/** What the voice line is doing. `thinking` = the voice model is preparing a reply. */
export type VoiceServerState = 'listening' | 'user_speaking' | 'thinking' | 'speaking';
export type VoiceSpeaker = 'user' | 'assistant';

export interface VoiceReadyMessage {
  type: 'ready';
  chat_id: string;
  input_sample_rate: number;
  output_sample_rate: number;
  model: string;
  /** true: words stream while the user speaks; false: only after; null: unmeasured. */
  live_captions?: boolean | null;
  /** Whether Suzent is already working in this chat when the call starts. */
  working?: boolean;
}
export interface VoiceStateMessage {
  type: 'state';
  state: VoiceServerState;
}
/** Suzent (the main agent) started or finished a delegated task. */
export interface VoiceWorkingMessage {
  type: 'working';
  active: boolean;
}
export interface VoiceTranscriptMessage {
  type: 'transcript';
  /** Unique per session and line; live and final updates of a line share it. */
  id: string;
  speaker: VoiceSpeaker;
  text: string;
  final: boolean;
}
export interface VoiceInterruptedMessage {
  type: 'interrupted';
}
export interface VoiceErrorMessage {
  type: 'error';
  code: string;
  message: string;
}
export interface VoiceClosedMessage {
  type: 'closed';
}
export type VoiceServerMessage =
  | VoiceReadyMessage
  | VoiceStateMessage
  | VoiceWorkingMessage
  | VoiceTranscriptMessage
  | VoiceInterruptedMessage
  | VoiceErrorMessage
  | VoiceClosedMessage;

export type VoiceClientMessage =
  { type: 'interrupt'; played_ms: number } | { type: 'stop' } | { type: 'text'; text: string };

export function parseVoiceServerMessage(value: string): VoiceServerMessage | null {
  try {
    const message = JSON.parse(value) as { type?: unknown };
    return typeof message.type === 'string' ? (message as VoiceServerMessage) : null;
  } catch {
    return null;
  }
}
