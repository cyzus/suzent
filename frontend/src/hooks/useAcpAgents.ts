import { useEffect, useState } from 'react';
import { fetchAcpAgents } from '../lib/api';
import type { AcpAgentDescriptor } from '../types/api';

/**
 * Shared, once-per-session view of the configured ACP agents.
 *
 * The registry only changes when the user edits acp_agents.json or installs an
 * adapter, so a single in-flight promise is shared across every consumer rather
 * than refetching per chat.
 */
let cached: Promise<AcpAgentDescriptor[]> | null = null;

export function invalidateAcpAgents(): void {
  cached = null;
}

export function useAcpAgents(): AcpAgentDescriptor[] {
  const [agents, setAgents] = useState<AcpAgentDescriptor[]>([]);

  useEffect(() => {
    if (!cached) cached = fetchAcpAgents().catch(() => []);
    let cancelled = false;
    void cached.then(items => { if (!cancelled) setAgents(items); });
    return () => { cancelled = true; };
  }, []);

  return agents;
}
