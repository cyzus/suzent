import { create } from 'zustand';
import type { HeartbeatStatus } from '../lib/api';

interface HeartbeatRunningState {
  // In-flight LLM turn: a heartbeat turn is actively streaming for a specific chat.
  // Set by ChatWindow event handlers via setRunning().
  inFlight: boolean;
  inFlightChatId: string | null;

  // Global runner status: polled from /heartbeat/status every 8s via App.tsx.
  loopRunning: boolean;
  lastPingAt: string | null;
  statusError: string | null;

  // Per-chat heartbeat status: populated by App.tsx 8s poll alongside global status.
  chatStatus: Record<string, HeartbeatStatus>;

  setRunning: (running: boolean, chatId: string | null) => void;
  setStatus: (status: HeartbeatStatus) => void;
  setChatStatus: (chatId: string, status: HeartbeatStatus) => void;
}

export const useHeartbeatRunning = create<HeartbeatRunningState>((set) => ({
  inFlight: false,
  inFlightChatId: null,
  loopRunning: false,
  lastPingAt: null,
  statusError: null,
  chatStatus: {},
  setRunning: (running, chatId) => set({ inFlight: running, inFlightChatId: chatId }),
  setStatus: (status) => {
    const s = status as any;
    set({
      loopRunning: status.running,
      lastPingAt: s.last_run_at ?? s.last_ping_at ?? null,
      statusError: s.last_error ?? s.error ?? null,
    });
  },
  setChatStatus: (chatId, status) => set(s => ({
    chatStatus: { ...s.chatStatus, [chatId]: status },
  })),
}));
