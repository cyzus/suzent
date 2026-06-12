import { useCallback, useEffect, useRef, useState } from 'react';

import { memoryApi } from '../lib/memoryApi';
import type { DreamStatus } from '../types/memory';

interface DreamStatusState {
  status: DreamStatus | null;
  loading: boolean;
  runningNow: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  runNow: () => Promise<void>;
}

const IDLE_POLL_MS = 30_000;
const ACTIVE_POLL_MS = 3_000;

export function useDreamStatus(): DreamStatusState {
  const [status, setStatus] = useState<DreamStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningNow, setRunningNow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await memoryApi.getDreamStatus();
      if (!mountedRef.current) return;
      setStatus(next);
      setError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load dream status');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const runNow = useCallback(async () => {
    setRunningNow(true);
    setError(null);
    try {
      const response = await memoryApi.consolidateMemory();
      if (!mountedRef.current) return;
      setStatus(prev => ({
        ...(prev ?? { active: true, available: true, enabled: true, running: false }),
        running: response.result.started ? true : false,
        phase: response.result.started ? 'queued' : prev?.phase,
        last_result: response.result,
      }));
      await refresh();
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to run dream consolidation');
      await refresh();
    } finally {
      if (mountedRef.current) setRunningNow(false);
    }
  }, [refresh]);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();

    let timerId: number | undefined;
    const tick = async () => {
      await refresh();
      if (!mountedRef.current) return;
      timerId = window.setTimeout(tick, status?.running ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    };
    timerId = window.setTimeout(tick, IDLE_POLL_MS);

    return () => {
      mountedRef.current = false;
      if (timerId !== undefined) window.clearTimeout(timerId);
    };
  }, [refresh, status?.running]);

  return { status, loading, runningNow, error, refresh, runNow };
}
