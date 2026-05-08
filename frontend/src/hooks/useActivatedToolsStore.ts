import { create } from 'zustand';

interface ActivatedToolsState {
  activatedByAI: Set<string>;
  addActivatedTools: (toolNames: string[]) => void;
  removeActivatedTool: (toolName: string) => void;
  clearActivatedTools: () => void;
}

export const useActivatedToolsStore = create<ActivatedToolsState>((set) => ({
  activatedByAI: new Set(),
  addActivatedTools: (toolNames) =>
    set((state) => {
      if (toolNames.every((n) => state.activatedByAI.has(n))) return state;
      return { activatedByAI: new Set([...state.activatedByAI, ...toolNames]) };
    }),
  removeActivatedTool: (toolName) =>
    set((state) => {
      const next = new Set(state.activatedByAI);
      next.delete(toolName);
      return { activatedByAI: next };
    }),
  clearActivatedTools: () => set({ activatedByAI: new Set() }),
}));
