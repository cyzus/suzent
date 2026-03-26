import { create } from 'zustand';

interface HeartbeatRunningState {
  // In-flight LLM turn: a heartbeat turn is actively streaming for a specific chat.
  // Set by ChatWindow event handlers via setRunning().
  inFlight: boolean;
  inFlightChatId: string | null;

  // Global runner status: polled from /heartbeat/status every 5 s via App.tsx.
  loopRunning: boolean;
  lastPingAt: string | null;
  statusError: string | null;

  setRunning: (running: boolean, chatId: string | null) => void;
  setStatus: (status: import('../lib/api').HeartbeatStatus) => void;
}

export const useHeartbeatRunning = create<HeartbeatRunningState>((set) => ({
  inFlight: false,
  inFlightChatId: null,
  loopRunning: false,
  lastPingAt: null,
  statusError: null,
  setRunning: (running, chatId) => set({ inFlight: running, inFlightChatId: chatId }),
  setStatus: (status) =>
    set({ loopRunning: status.running, lastPingAt: status.last_run_at, statusError: status.last_error }),
}));
