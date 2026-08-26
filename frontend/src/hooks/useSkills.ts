/**
 * Skills state management hook using Zustand
 */

import { create } from 'zustand';
import { Skill } from '../types/skills';
import * as skillsApi from '../lib/skillsApi';

interface SkillsState {
  skills: Skill[];
  loading: boolean;
  error: string | null;

  // Actions
  loadSkills: (chatId?: string | null) => Promise<void>;
  reload: (chatId?: string | null) => Promise<void>;
  toggle: (id: string, chatId?: string | null) => Promise<void>;
}

export const useSkills = create<SkillsState>((set, get) => ({
  skills: [],
  loading: false,
  error: null,

  loadSkills: async (chatId) => {
    set({ loading: true, error: null });
    try {
      const skills = await skillsApi.fetchSkills(chatId);
      set({ skills, loading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load skills',
        loading: false,
      });
    }
  },

  reload: async (chatId) => {
    set({ loading: true, error: null });
    try {
      await skillsApi.reloadSkills(chatId);
      const skills = await skillsApi.fetchSkills(chatId);
      set({ skills, loading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to reload skills',
        loading: false,
      });
    }
  },

  toggle: async (id: string, chatId?: string | null) => {
    const skill = get().skills.find((s) => s.id === id);
    if (!skill) return;

    const newEnabled = !skill.enabled;

    // Optimistic update
    set((state) => ({
      skills: state.skills.map((s) => (s.id === id ? { ...s, enabled: newEnabled } : s)),
    }));

    try {
      await skillsApi.toggleSkill(id, newEnabled, chatId);
      // Success - keep optimistic update
    } catch (error) {
      // Revert on error
      set((state) => ({
        skills: state.skills.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s)),
        error: error instanceof Error ? error.message : 'Failed to toggle skill',
      }));
    }
  },
}));
