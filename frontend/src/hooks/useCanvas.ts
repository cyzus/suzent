/**
 * useCanvas — canvas surface state for A2UI with localStorage persistence.
 *
 * Surfaces are keyed by id; calling setSurface with an existing id is an upsert.
 * State is persisted per chatId so reloading the page restores the canvas.
 * When chatId changes the in-memory state is replaced from localStorage.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import type { A2UISurface } from '../types/a2ui';

const storageKey = (chatId: string) => `a2ui_surfaces:${chatId}`;

function loadFromStorage(chatId: string): A2UISurface[] {
  if (!chatId) return [];
  try {
    const raw = localStorage.getItem(storageKey(chatId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveToStorage(chatId: string, surfaces: A2UISurface[]): void {
  if (!chatId) return;
  try {
    localStorage.setItem(storageKey(chatId), JSON.stringify(surfaces));
  } catch {
    // Ignore quota errors
  }
}

export interface CanvasState {
  /** Ordered list of surfaces (insertion order preserved) */
  surfaces: A2UISurface[];
  /** Currently focused surface id */
  activeSurfaceId: string | null;
  /** True when at least one surface exists */
  hasSurfaces: boolean;
  /** Upsert a surface. Auto-activates if it's the first one. */
  setSurface: (surface: A2UISurface) => void;
  /** Focus a specific surface by id */
  setActiveSurface: (id: string) => void;
  /** Clear all surfaces and remove from localStorage */
  clearSurfaces: () => void;
}

export function useCanvas(chatId: string | null): CanvasState {
  // Initialize from localStorage for the current chat
  const [surfaces, setSurfaces] = useState<A2UISurface[]>(() =>
    chatId ? loadFromStorage(chatId) : []
  );
  const [activeSurfaceId, setActiveSurfaceId] = useState<string | null>(() => {
    const initial = chatId ? loadFromStorage(chatId) : [];
    return initial.length > 0 ? initial[0].id : null;
  });

  // Track previous chatId to detect chat switches
  const prevChatIdRef = useRef<string | null>(chatId);

  // When chatId changes, reload surfaces from localStorage
  useEffect(() => {
    if (prevChatIdRef.current === chatId) return;
    prevChatIdRef.current = chatId;

    const loaded = chatId ? loadFromStorage(chatId) : [];
    setSurfaces(loaded);
    setActiveSurfaceId(loaded.length > 0 ? loaded[0].id : null);
  }, [chatId]);

  const setSurface = useCallback((surface: A2UISurface) => {
    setSurfaces(prev => {
      const idx = prev.findIndex(s => s.id === surface.id);
      const next = idx >= 0
        ? prev.map((s, i) => i === idx ? surface : s)
        : [...prev, surface];
      if (chatId) saveToStorage(chatId, next);
      return next;
    });
    setActiveSurfaceId(prev => prev ?? surface.id);
  }, [chatId]);

  const setActiveSurface = useCallback((id: string) => {
    setActiveSurfaceId(id);
  }, []);

  const clearSurfaces = useCallback(() => {
    setSurfaces([]);
    setActiveSurfaceId(null);
    if (chatId) {
      try { localStorage.removeItem(storageKey(chatId)); } catch { /* ignore */ }
    }
  }, [chatId]);

  return {
    surfaces,
    activeSurfaceId,
    hasSurfaces: surfaces.length > 0,
    setSurface,
    setActiveSurface,
    clearSurfaces,
  };
}
