import { create } from 'zustand';

export interface ContextUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  context_tokens?: number | null;
  /**
   * Context window of the model this chat runs on, as resolved by the backend.
   * Absent until the first turn reports it — fall back to the backend config's
   * `maxContextTokens` then, never to a hardcoded number.
   */
  context_limit?: number | null;
  cache_write_tokens: number;
  cache_read_tokens: number;
  requests: number;
  details?: Record<string, number>;
}

/**
 * Mid-run usage reported by the backend before each model request. Only
 * `context_tokens` is always present — the cumulative counters are omitted while
 * they are still zero so they can be merged over the previous turn's numbers
 * instead of blanking the panel at the start of every run.
 */
export type PartialContextUsage = Partial<ContextUsage> & { context_tokens?: number | null };

/** Lifecycle of a compaction pass, whoever started it. */
export interface CompactionActivity {
  /** True while a pass is in flight — drives the panel's running animation. */
  active: boolean;
  stage: 'start' | 'complete' | 'skipped' | 'error';
  /** 'auto' / 'auto_midrun' for agent-triggered, 'manual' / 'command' otherwise. */
  source: string;
  label: string;
}

const EMPTY_USAGE: ContextUsage = {
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
  context_tokens: 0,
  cache_write_tokens: 0,
  cache_read_tokens: 0,
  requests: 0,
};

interface ContextUsageState {
  usage: ContextUsage | null;
  usageByChatId: Record<string, ContextUsage>;
  compaction: CompactionActivity | null;
  setUsage: (usage: ContextUsage) => void;
  setUsageForChat: (chatId: string, usage: ContextUsage) => void;
  mergeUsageForChat: (chatId: string, usage: PartialContextUsage) => void;
  getUsageForChat: (chatId: string) => ContextUsage | null;
  clearUsage: () => void;
  setCompaction: (compaction: CompactionActivity | null) => void;
  clearCompaction: () => void;
}

export const useContextUsageStore = create<ContextUsageState>((set, get) => ({
  usage: null,
  usageByChatId: {},
  compaction: null,
  setUsage: (usage) => set({ usage }),
  setUsageForChat: (chatId, usage) =>
    set((state) => ({
      usage,
      usageByChatId: {
        ...state.usageByChatId,
        [chatId]: usage,
      },
    })),
  mergeUsageForChat: (chatId, partial) =>
    set((state) => {
      // Never fall back to the global `usage`: it belongs to whichever chat was
      // last active, and merging into it would show one chat's counters under
      // another chat's context size.
      const base = state.usageByChatId[chatId] ?? EMPTY_USAGE;
      const defined = Object.fromEntries(
        Object.entries(partial).filter(([, value]) => value !== undefined && value !== null)
      ) as Partial<ContextUsage>;
      const merged: ContextUsage = { ...base, ...defined };
      return {
        usage: merged,
        usageByChatId: { ...state.usageByChatId, [chatId]: merged },
      };
    }),
  getUsageForChat: (chatId) => get().usageByChatId[chatId] ?? null,
  clearUsage: () => set({ usage: null }),
  setCompaction: (compaction) => set({ compaction }),
  clearCompaction: () => set({ compaction: null }),
}));
