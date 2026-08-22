import { create } from 'zustand';

export type StatusType = 'idle' | 'info' | 'success' | 'error' | 'warning';

interface StatusState {
  message: string | null;
  type: StatusType;
  timeoutId: NodeJS.Timeout | null;
  
  setStatus: (message: string, type?: StatusType, duration?: number) => void;
  clearStatus: () => void;
}

export const useStatusStore = create<StatusState>((set, get) => ({
  message: null,
  type: 'idle',
  timeoutId: null,

  setStatus: (message: string, type: StatusType = 'info', duration: number = 3000) => {
    const { timeoutId } = get();
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    const newTimeoutId = setTimeout(() => {
      set({ message: null, type: 'idle', timeoutId: null });
    }, duration);

    set({ message, type, timeoutId: newTimeoutId });
  },

  clearStatus: () => {
    const { timeoutId } = get();
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    set({ message: null, type: 'idle', timeoutId: null });
  },
}));
