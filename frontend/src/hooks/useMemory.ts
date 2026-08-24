/**
 * Memory state management hook using Zustand
 */

import { create } from 'zustand';
import type {
  CoreMemoryBlocks,
  CoreMemoryLabel,
  ArchivalMemory,
  ArchivalQueryOptions,
  MemoryFacets,
  MemoryStats,
} from '../types/memory';
import { memoryApi } from '../lib/memoryApi';

interface MemoryState {
  // Core memory
  coreMemory: CoreMemoryBlocks | null;
  coreMemoryLoading: boolean;
  coreMemoryError: string | null;

  // Archival memory
  archivalMemories: ArchivalMemory[];
  archivalLoading: boolean;
  archivalError: string | null;
  archivalHasMore: boolean;
  archivalQuery: string;
  /** Size of the whole matching set, when the server can report one. */
  archivalTotal: number | null;
  /** Facet counts for the filter bar; null until a first page has come back. */
  archivalFacets: MemoryFacets | null;

  // Stats
  stats: MemoryStats | null;
  statsLoading: boolean;

  // User context
  userId: string;

  // Actions
  setUserId: (userId: string) => void;
  loadCoreMemory: (chatId?: string | null) => Promise<void>;
  updateCoreMemoryBlock: (label: CoreMemoryLabel, content: string) => Promise<void>;
  loadArchivalMemories: (
    query?: string,
    append?: boolean,
    options?: ArchivalQueryOptions
  ) => Promise<void>;
  deleteArchivalMemory: (memoryId: string) => Promise<void>;
  loadStats: () => Promise<void>;
  reset: () => void;
}

const initialState = {
  coreMemory: null,
  coreMemoryLoading: false,
  coreMemoryError: null,
  archivalMemories: [],
  archivalLoading: false,
  archivalError: null,
  archivalHasMore: true,
  archivalQuery: '',
  archivalTotal: null,
  archivalFacets: null,
  stats: null,
  statsLoading: false,
  userId: 'default-user',
};

// Sort/filter changes fire overlapping requests; only the newest may write state.
let archivalRequestId = 0;

export const useMemory = create<MemoryState>((set, get) => ({
  ...initialState,

  setUserId: (userId: string) => {
    set({ userId });
  },

  loadCoreMemory: async (chatId?: string | null) => {
    set({ coreMemoryLoading: true, coreMemoryError: null });
    try {
      const blocks = await memoryApi.getCoreMemory(get().userId, chatId);
      set({ coreMemory: blocks, coreMemoryLoading: false });
    } catch (error) {
      set({
        coreMemoryError: error instanceof Error ? error.message : 'Failed to load core memory',
        coreMemoryLoading: false,
      });
    }
  },

  updateCoreMemoryBlock: async (label: CoreMemoryLabel, content: string) => {
    try {
      await memoryApi.updateCoreMemoryBlock(label, content, get().userId);

      // Update local state
      set(state => ({
        coreMemory: state.coreMemory
          ? { ...state.coreMemory, [label]: content }
          : null,
      }));
    } catch (error) {
      set({
        coreMemoryError: error instanceof Error ? error.message : 'Failed to update core memory',
      });
      throw error;
    }
  },

  loadArchivalMemories: async (
    query: string = '',
    append: boolean = false,
    options: ArchivalQueryOptions = {}
  ) => {
    const state = get();

    // Appending races with itself (scroll spam), but a fresh load must always win —
    // it carries a new sort or filter that the in-flight page no longer matches.
    if (state.archivalLoading && append) return;

    const requestId = ++archivalRequestId;
    set({ archivalLoading: true, archivalError: null, archivalQuery: query });

    try {
      const offset = append ? state.archivalMemories.length : 0;
      const result = await memoryApi.searchArchivalMemory(
        query,
        state.userId,
        20,
        offset,
        // Facets describe the whole set, so they are fetched with the first page
        // and reused for every "load more" after it.
        { ...options, withFacets: !append }
      );

      if (requestId !== archivalRequestId) return;

      set(state => ({
        archivalMemories: append
          ? [...state.archivalMemories, ...result.memories]
          : result.memories,
        archivalLoading: false,
        archivalHasMore: result.memories.length === result.limit,
        archivalTotal: result.total ?? null,
        // Facets only come back on a first page. Keeping the previous ones on an
        // append stops the filter bar from emptying itself as you scroll.
        archivalFacets: result.facets ?? state.archivalFacets,
      }));
    } catch (error) {
      if (requestId !== archivalRequestId) return;
      set({
        archivalError: error instanceof Error ? error.message : 'Failed to load archival memories',
        archivalLoading: false,
      });
    }
  },

  deleteArchivalMemory: async (memoryId: string) => {
    try {
      await memoryApi.deleteArchivalMemory(memoryId);

      // Remove from local state
      set(state => ({
        archivalMemories: state.archivalMemories.filter(m => m.id !== memoryId),
        archivalTotal: state.archivalTotal === null ? null : Math.max(state.archivalTotal - 1, 0),
      }));

      // Reload stats
      get().loadStats();
    } catch (error) {
      set({
        archivalError: error instanceof Error ? error.message : 'Failed to delete memory',
      });
      throw error;
    }
  },

  loadStats: async () => {
    set({ statsLoading: true });
    try {
      const stats = await memoryApi.getMemoryStats(get().userId);
      set({ stats, statsLoading: false });
    } catch (error) {
      console.error('Failed to load memory stats:', error);
      set({ statsLoading: false });
    }
  },

  reset: () => {
    set(initialState);
  },
}));
