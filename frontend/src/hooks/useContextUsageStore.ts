import { create } from 'zustand';

export interface ContextUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  context_tokens?: number | null;
  cache_write_tokens: number;
  cache_read_tokens: number;
  requests: number;
  details?: Record<string, number>;
}

interface ContextUsageState {
  usage: ContextUsage | null;
  usageByChatId: Record<string, ContextUsage>;
  compactNotice: string | null;
  setUsage: (usage: ContextUsage) => void;
  setUsageForChat: (chatId: string, usage: ContextUsage) => void;
  getUsageForChat: (chatId: string) => ContextUsage | null;
  clearUsage: () => void;
  setCompactNotice: (notice: string | null) => void;
  clearCompactNotice: () => void;
}

export const useContextUsageStore = create<ContextUsageState>((set, get) => ({
  usage: null,
  usageByChatId: {},
  compactNotice: null,
  setUsage: (usage) => set({ usage }),
  setUsageForChat: (chatId, usage) => set((state) => ({
    usage,
    usageByChatId: {
      ...state.usageByChatId,
      [chatId]: usage,
    },
  })),
  getUsageForChat: (chatId) => get().usageByChatId[chatId] ?? null,
  clearUsage: () => set({ usage: null }),
  setCompactNotice: (compactNotice) => set({ compactNotice }),
  clearCompactNotice: () => set({ compactNotice: null }),
}));
