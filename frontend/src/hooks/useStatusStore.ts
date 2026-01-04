import { create } from 'zustand';

export type StatusType = 'idle' | 'info' | 'success' | 'error' | 'warning';

interface StatusState {
  message: string;
  type: StatusType;
  timeoutId: NodeJS.Timeout | null;
  
  setStatus: (message: string, type?: StatusType, duration?: number) => void;
  clearStatus: () => void;
}

export const useStatusStore = create<StatusState>((set, get) => ({
  message: 'SYSTEM_READY',
  type: 'idle',
  timeoutId: null,

  setStatus: (message: string, type: StatusType = 'info', duration: number = 3000) => {
    const { timeoutId } = get();
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    const newTimeoutId = setTimeout(() => {
      set({ message: 'SYSTEM_READY', type: 'idle', timeoutId: null });
    }, duration);

    set({ message, type, timeoutId: newTimeoutId });
  },

  clearStatus: () => {
    const { timeoutId } = get();
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    set({ message: 'SYSTEM_READY', type: 'idle', timeoutId: null });
  },
}));
