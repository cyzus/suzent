import { useCallback, useEffect, useRef, useState } from 'react';

import { memoryApi } from '../lib/memoryApi';
import type { DreamStatus } from '../types/memory';

interface DreamStatusState {
  status: DreamStatus | null;
  loading: boolean;
  runningIngest: boolean;
  runningLint: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  runIngest: () => Promise<void>;
  runLint: () => Promise<void>;
}

const IDLE_POLL_MS = 30_000;
const ACTIVE_POLL_MS = 3_000;

export function useDreamStatus(): DreamStatusState {
  const [status, setStatus] = useState<DreamStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningIngest, setRunningIngest] = useState(false);
  const [runningLint, setRunningLint] = useState(false);
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

  const runPhase = useCallback(async (phase: 'ingest' | 'lint') => {
    if (phase === 'ingest') {
      setRunningIngest(true);
    } else {
      setRunningLint(true);
    }
    setError(null);
    try {
      const response = phase === 'ingest'
        ? await memoryApi.consolidateMemory()
        : await memoryApi.lintMemory();
      if (!mountedRef.current) return;
      setStatus(prev => ({
        ...(prev ?? { active: true, available: true, enabled: true, running: false }),
        running: response.result.started ? true : false,
        phase: response.result.started ? 'queued' : prev?.phase,
        last_result: phase === 'ingest' ? response.result : prev?.last_result,
        last_ingest_result: phase === 'ingest' ? response.result : prev?.last_ingest_result,
        last_lint_result: phase === 'lint' ? response.result : prev?.last_lint_result,
      }));
      await refresh();
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to run dream agent');
      await refresh();
    } finally {
      if (mountedRef.current) {
        if (phase === 'ingest') {
          setRunningIngest(false);
        } else {
          setRunningLint(false);
        }
      }
    }
  }, [refresh]);

  const runIngest = useCallback(async () => {
    await runPhase('ingest');
  }, [runPhase]);

  const runLint = useCallback(async () => {
    await runPhase('lint');
  }, [runPhase]);

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

  return { status, loading, runningIngest, runningLint, error, refresh, runIngest, runLint };
}
