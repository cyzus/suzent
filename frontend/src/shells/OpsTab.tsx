import React, { useCallback, useEffect, useState } from 'react';
import { ArrowPathIcon, ServerStackIcon } from '@heroicons/react/24/outline';

import { useI18n } from '../i18n';
import { BrutalButton } from '../components/BrutalButton';
import { BrutalOnOff } from '../components/BrutalOnOff';
import { SectionCardHeader, SettingsCard, SettingsPage } from '../components/settings/SettingsCard';
import { SettingsHeader } from '../components/settings/SettingsHeader';
import { ServiceLogCard } from '../components/settings/ServiceLogCard';
import {
  fetchOpsStatus,
  OpsError,
  restartOpsService,
  setOpsServiceEnabled,
  type OpsServiceStatus,
} from '../lib/opsApi';

const STATUS_POLL_MS = 5000;

// How long to keep asking after a self-restart before calling it a failure.
// A cold start re-opens the database and reloads channel drivers, so it is
// routinely slower than a health check.
const RECONNECT_TIMEOUT_MS = 60_000;
const RECONNECT_INTERVAL_MS = 1000;

function formatUptime(seconds: number | null): string {
  if (seconds === null) return '—';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
}

function formatMemory(bytes: number | null): string {
  if (bytes === null) return '—';
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

interface StatCellProps {
  label: string;
  value: string;
}

function StatCell({ label, value }: StatCellProps): React.ReactElement {
  return (
    <div className="border-2 border-brutal-black bg-neutral-50 p-3 dark:bg-zinc-900">
      <div className="uppercase text-neutral-500">{label}</div>
      <div className="mt-1 font-bold">{value}</div>
    </div>
  );
}

/**
 * Service operations, for the client that cannot use Tauri.
 *
 * The desktop app's equivalent tab assumes the host is the machine in front of
 * you, so it can afford to be a status readout with a couple of buttons. Here
 * the host is somewhere else, and the two things that follow from that shape
 * this page: a restart may take the page's own backend down (so it reconnects
 * rather than reporting a network error), and the log is the only account of
 * what went wrong (so it is on the page, not a path to go find over SSH).
 */
export function OpsTab(): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<OpsServiceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Turn a failure into something an operator can act on.
   *
   * A bare `fetch` rejection reads "Failed to fetch", which in this page means
   * the host is gone -- the single most important thing the console has to
   * say, and the one case where the browser's own wording explains nothing.
   */
  const describe = useCallback(
    (failure: unknown): string => {
      if (failure instanceof OpsError) return failure.message;
      return t('console.ops.unreachable');
    },
    [t]
  );

  const refreshStatus = useCallback(
    async (signal?: AbortSignal): Promise<void> => {
      try {
        setStatus(await fetchOpsStatus(signal));
        setError(null);
      } catch (statusError) {
        if (signal?.aborted) return;
        setError(describe(statusError));
      }
    },
    [describe]
  );

  useEffect(() => {
    const controller = new AbortController();
    void refreshStatus(controller.signal);
    const timer = window.setInterval(() => {
      if (!reconnecting) void refreshStatus();
    }, STATUS_POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refreshStatus, reconnecting]);

  /**
   * Poll until the host answers again.
   *
   * A self-restart deliberately drops this page's backend. Without this the
   * console would show a connection error for the whole gap and leave the
   * operator unsure whether they had just broken their own server.
   */
  const waitForHost = useCallback(async (): Promise<void> => {
    setReconnecting(true);
    const deadline = Date.now() + RECONNECT_TIMEOUT_MS;
    try {
      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, RECONNECT_INTERVAL_MS));
        try {
          const fresh = await fetchOpsStatus();
          setStatus(fresh);
          setError(null);
          return;
        } catch {
          // Expected while it is down.
        }
      }
      setError(t('console.ops.reconnectTimeout'));
    } finally {
      setReconnecting(false);
    }
  }, [t]);

  const restart = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const immediate = await restartOpsService();
      if (immediate === null) {
        await waitForHost();
      } else {
        setStatus(immediate);
      }
    } catch (restartError) {
      setError(describe(restartError));
    } finally {
      setBusy(false);
    }
  };

  const setEnabled = async (enabled: boolean): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      setStatus(await setOpsServiceEnabled(enabled));
    } catch (toggleError) {
      if (toggleError instanceof OpsError && toggleError.code === 'would_disable_self') {
        setError(t('console.ops.cannotDisableSelf'));
      } else {
        setError(describe(toggleError));
      }
    } finally {
      setBusy(false);
    }
  };

  const stateLabel = !status?.installed
    ? t('console.ops.notInstalled')
    : status.ready
      ? t('console.ops.ready')
      : status.running
        ? t('console.ops.starting')
        : t('console.ops.stopped');

  return (
    <SettingsPage>
      <SettingsHeader title={t('console.ops.title')} subtitle={t('console.ops.subtitle')} />

      <SettingsCard>
        <SectionCardHeader
          iconTone={status?.ready ? 'green' : 'neutral'}
          icon={<ServerStackIcon className="h-6 w-6" />}
          title={t('console.ops.serviceTitle')}
          description={t('console.ops.serviceDesc')}
          actions={
            <BrutalOnOff
              checked={status?.installed ?? false}
              disabled={busy || reconnecting || status === null}
              onChange={(enabled) => void setEnabled(enabled)}
            />
          }
        />

        <div className="grid grid-cols-2 gap-3 font-mono text-xs md:grid-cols-4">
          <StatCell label={t('console.ops.status')} value={stateLabel} />
          <StatCell
            label={t('console.ops.uptime')}
            value={formatUptime(status?.uptimeSeconds ?? null)}
          />
          <StatCell
            label={t('console.ops.memory')}
            value={formatMemory(status?.rssBytes ?? null)}
          />
          <StatCell label="PID" value={status?.pid == null ? '—' : String(status.pid)} />
        </div>

        {status?.port && (
          <p className="mt-4 font-mono text-xs text-neutral-500">
            127.0.0.1:{status.port} · v{status.version ?? '—'}
          </p>
        )}

        {status?.selfManaged && (
          <p className="mt-2 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400">
            {t('console.ops.selfManagedNote')}
          </p>
        )}

        {reconnecting && (
          <div
            role="status"
            className="mt-4 flex items-center gap-2 border-2 border-brutal-black bg-brutal-yellow p-3 font-mono text-sm text-brutal-black"
          >
            <ArrowPathIcon className="h-4 w-4 animate-spin" aria-hidden="true" />
            {t('console.ops.reconnecting')}
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-4 border-2 border-brutal-black bg-red-100 p-3 font-mono text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
          >
            {error}
          </div>
        )}

        <div className="mt-6 flex flex-wrap gap-3">
          <BrutalButton
            variant="warning"
            disabled={busy || reconnecting || !status?.installed}
            onClick={() => void restart()}
          >
            {t('console.ops.restart')}
          </BrutalButton>
        </div>
      </SettingsCard>

      <ServiceLogCard paused={reconnecting} />
    </SettingsPage>
  );
}
