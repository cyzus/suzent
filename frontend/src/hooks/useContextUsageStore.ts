import { create } from 'zustand';

export interface ContextUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_write_tokens: number;
  cache_read_tokens: number;
  requests: number;
  details?: Record<string, number>;
}

interface ContextUsageState {
  usage: ContextUsage | null;
  setUsage: (usage: ContextUsage) => void;
  clearUsage: () => void;
}

export const useContextUsageStore = create<ContextUsageState>((set) => ({
  usage: null,
  setUsage: (usage) => set({ usage }),
  clearUsage: () => set({ usage: null }),
}));
