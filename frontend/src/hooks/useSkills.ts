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
    loadSkills: () => Promise<void>;
    reload: () => Promise<void>;
    toggle: (name: string) => Promise<void>;
}

export const useSkills = create<SkillsState>((set, get) => ({
    skills: [],
    loading: false,
    error: null,

    loadSkills: async () => {
        set({ loading: true, error: null });
        try {
            const skills = await skillsApi.fetchSkills();
            set({ skills, loading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : 'Failed to load skills',
                loading: false,
            });
        }
    },

    reload: async () => {
        set({ loading: true, error: null });
        try {
            await skillsApi.reloadSkills();
            const skills = await skillsApi.fetchSkills();
            set({ skills, loading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : 'Failed to reload skills',
                loading: false
            });
        }
    },

    toggle: async (name: string) => {
        const skill = get().skills.find(s => s.name === name);
        if (!skill) return;

        const newEnabled = !skill.enabled;

        // Optimistic update
        set((state) => ({
            skills: state.skills.map((s) =>
                s.name === name ? { ...s, enabled: newEnabled } : s
            ),
        }));

        try {
            await skillsApi.toggleSkill(name, newEnabled);
            // Success - keep optimistic update
        } catch (error) {
            // Revert on error
            set((state) => ({
                skills: state.skills.map((s) =>
                    s.name === name ? { ...s, enabled: !s.enabled } : s
                ),
                error: error instanceof Error ? error.message : 'Failed to toggle skill'
            }));
        }
    }
}));
