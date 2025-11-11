/**
 * Memory state management hook using Zustand
 */

import { create } from 'zustand';
import type {
  CoreMemoryBlocks,
  CoreMemoryLabel,
  ArchivalMemory,
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

  // Stats
  stats: MemoryStats | null;
  statsLoading: boolean;

  // User context
  userId: string;

  // Actions
  setUserId: (userId: string) => void;
  loadCoreMemory: () => Promise<void>;
  updateCoreMemoryBlock: (label: CoreMemoryLabel, content: string) => Promise<void>;
  loadArchivalMemories: (query?: string, append?: boolean) => Promise<void>;
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
  stats: null,
  statsLoading: false,
  userId: 'default-user',
};

export const useMemory = create<MemoryState>((set, get) => ({
  ...initialState,

  setUserId: (userId: string) => {
    set({ userId });
  },

  loadCoreMemory: async () => {
    set({ coreMemoryLoading: true, coreMemoryError: null });
    try {
      const blocks = await memoryApi.getCoreMemory(get().userId);
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

  loadArchivalMemories: async (query: string = '', append: boolean = false) => {
    const state = get();

    // Don't load if already loading
    if (state.archivalLoading) return;

    set({ archivalLoading: true, archivalError: null, archivalQuery: query });

    try {
      const offset = append ? state.archivalMemories.length : 0;
      const result = await memoryApi.searchArchivalMemory(query, state.userId, 20, offset);

      set(state => ({
        archivalMemories: append
          ? [...state.archivalMemories, ...result.memories]
          : result.memories,
        archivalLoading: false,
        archivalHasMore: result.memories.length === result.limit,
      }));
    } catch (error) {
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
