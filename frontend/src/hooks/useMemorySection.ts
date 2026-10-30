import { useEffect, useRef, useState } from 'react';
import { memoryApi } from '../lib/memoryApi';
import type { ChatMemoryActivity } from '../types/memory';
import { useChatCoreStore } from './useChatStore';
import { useEventBus } from './useEventBus';

export interface MemorySection {
  enabled: boolean;
  /** This chat's memory extraction is running right now. */
  extracting: boolean;
  activity: ChatMemoryActivity | null;
  /** Keys of facts saved since this chat was opened. */
  fresh: ReadonlySet<string>;
}

const NONE: ReadonlySet<string> = new Set();

export function savedFactKey(fact: ChatMemoryActivity['saved'][number]): string {
  return `${fact.date}-${fact.time}-${fact.content}`;
}

export function useMemorySection(chatId: string | null | undefined): MemorySection {
  const { config, backendConfig } = useChatCoreStore();
  const enabled = !!(config?.memory_enabled ?? backendConfig?.userPreferences?.memory_enabled);
  const { activeStreams, memoryChats } = useEventBus();
  const streaming = !!chatId && activeStreams.has(chatId);
  const extracting = !!chatId && memoryChats.has(chatId);
  const [activity, setActivity] = useState<ChatMemoryActivity | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [fresh, setFresh] = useState<ReadonlySet<string>>(NONE);
  const seen = useRef<{ chatId: string; keys: Set<string> } | null>(null);

  // A turn ending brings a new recall; extraction ending brings newly saved facts.
  useEffect(() => {
    if (!chatId || !enabled) return;
    let cancelled = false;
    memoryApi
      .getChatMemoryActivity(chatId)
      .then((next) => {
        if (cancelled) return;
        const keys = new Set(next.saved.map(savedFactKey));
        const before = seen.current?.chatId === chatId ? seen.current.keys : null;
        // The first load is what the chat already had; only later arrivals are new.
        setFresh((prev) => {
          if (!before) return NONE;
          const added = [...keys].filter((key) => !before.has(key));
          return added.length > 0 ? new Set([...prev, ...added]) : prev;
        });
        seen.current = { chatId, keys };
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

  const current = loadedFor === chatId;
  return {
    enabled,
    extracting,
    activity: current ? activity : null,
    fresh: current ? fresh : NONE,
  };
}
