import { useEffect, useState } from 'react';
import { fetchAcpAgents } from '../lib/api';
import type { AcpAgentDescriptor } from '../types/api';

/**
 * Shared, reactive view of the configured ACP agents.
 *
 * The registry changes when the user edits acp_agents.json or enables an
 * adapter in Settings. A single in-flight promise is shared across consumers,
 * and `invalidateAcpAgents()` notifies every mounted subscriber to refresh so
 * the chat engine picker updates immediately after an adapter is enabled.
 */
let cached: Promise<AcpAgentDescriptor[]> | null = null;
const listeners = new Set<() => void>();

export function invalidateAcpAgents(): void {
  cached = null;
  for (const listener of listeners) {
    listener();
  }
}

export function useAcpAgents(): AcpAgentDescriptor[] {
  const [agents, setAgents] = useState<AcpAgentDescriptor[]>([]);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const onInvalidate = () => setRevision((r) => r + 1);
    listeners.add(onInvalidate);
    return () => {
      listeners.delete(onInvalidate);
    };
  }, []);

  useEffect(() => {
    if (!cached) cached = fetchAcpAgents().catch(() => []);
    let cancelled = false;
    void cached.then((items) => {
      if (!cancelled) setAgents(items);
    });
    return () => {
      cancelled = true;
    };
  }, [revision]);

  return agents;
}
