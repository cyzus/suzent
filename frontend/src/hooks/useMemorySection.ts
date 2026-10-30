import { useEffect, useState } from 'react';
import { memoryApi } from '../lib/memoryApi';
import type { ChatMemoryActivity } from '../types/memory';
import { useChatCoreStore } from './useChatStore';
import { useEventBus } from './useEventBus';

export interface MemorySection {
  enabled: boolean;
  /** This chat's memory extraction is running right now. */
  extracting: boolean;
  activity: ChatMemoryActivity | null;
}

export function useMemorySection(chatId: string | null | undefined): MemorySection {
  const { config, backendConfig } = useChatCoreStore();
  const enabled = !!(config?.memory_enabled ?? backendConfig?.userPreferences?.memory_enabled);
  const { activeStreams, memoryChats } = useEventBus();
  const streaming = !!chatId && activeStreams.has(chatId);
  const extracting = !!chatId && memoryChats.has(chatId);
  const [activity, setActivity] = useState<ChatMemoryActivity | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  // A turn ending brings a new recall; extraction ending brings newly saved facts.
  useEffect(() => {
    if (!chatId || !enabled) return;
    let cancelled = false;
    memoryApi
      .getChatMemoryActivity(chatId)
      .then((next) => {
        if (cancelled) return;
        setActivity(next);
        setLoadedFor(chatId);
      })
      .catch(() => {
        // A new chat may not exist on the server yet; the section just stays empty.
        if (cancelled) return;
        setActivity(null);
        setLoadedFor(chatId);
      });
    return () => {
      cancelled = true;
    };
  }, [chatId, enabled, streaming, extracting]);

  return { enabled, extracting, activity: loadedFor === chatId ? activity : null };
}
