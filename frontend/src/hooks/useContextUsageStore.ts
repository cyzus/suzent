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
  compactNotice: string | null;
  setUsage: (usage: ContextUsage) => void;
  clearUsage: () => void;
  setCompactNotice: (notice: string | null) => void;
  clearCompactNotice: () => void;
}

export const useContextUsageStore = create<ContextUsageState>((set) => ({
  usage: null,
  compactNotice: null,
  setUsage: (usage) => set({ usage }),
  clearUsage: () => set({ usage: null }),
  setCompactNotice: (compactNotice) => set({ compactNotice }),
  clearCompactNotice: () => set({ compactNotice: null }),
}));
