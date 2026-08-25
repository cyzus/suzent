import React, { useCallback, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { BrutalOnOff } from '../BrutalOnOff';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

interface ServiceStatus {
  installed: boolean;
  autostart: boolean;
  running: boolean;
  ready: boolean;
  pid: number | null;
  port: number | null;
  version: string | null;
  uptime_seconds: number | null;
  rss_bytes: number | null;
  error: string | null;
}

function parseStatus(raw: string): ServiceStatus {
  return JSON.parse(raw) as ServiceStatus;
}

function formatUptime(seconds: number | null): string {
  if (seconds === null) return '—';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function BackgroundServiceTab(): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const raw = await invoke<string>('get_service_status');
      setStatus(parseStatus(raw));
      setError(null);
    } catch (refreshError) {
      setError(String(refreshError));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const setEnabled = async (enabled: boolean): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const raw = await invoke<string>('set_service_enabled', { enabled });
      setStatus(parseStatus(raw));
      window.setTimeout(() => void refresh(), 1500);
    } catch (actionError) {
      setError(String(actionError));
    } finally {
      setBusy(false);
    }
  };

  const restart = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await invoke<string>('restart_background_service');
      window.setTimeout(() => void refresh(), 1500);
    } catch (actionError) {
      setError(String(actionError));
    } finally {
      setBusy(false);
    }
  };

  const copyLogPath = async (): Promise<void> => {
    try {
      const path = await invoke<string>('get_service_log_path');
      await navigator.clipboard.writeText(path);
    } catch (copyError) {
      setError(String(copyError));
    }
  };

  const memory =
    status?.rss_bytes == null ? '—' : `${(status.rss_bytes / 1024 / 1024).toFixed(1)} MiB`;
  const stateLabel = !status?.installed
    ? t('settings.service.notInstalled')
    : status.ready
      ? t('settings.service.ready')
      : status.running
        ? t('settings.service.starting')
        : t('settings.service.stopped');

  return (
    <SettingsPage>
      <SettingsHeader
        title={t('settings.service.title')}
        subtitle={t('settings.service.subtitle')}
      />

      <SettingsCard>
        <SectionCardHeader
          iconTone={status?.ready ? 'green' : 'neutral'}
          icon={
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"
              />
            </svg>
          }
          title={t('settings.service.backgroundTitle')}
          description={t('settings.service.backgroundDesc')}
          actions={
            <BrutalOnOff
              checked={status?.installed ?? false}
              disabled={busy || status === null}
              onChange={(enabled) => void setEnabled(enabled)}
            />
          }
        />

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
          <div className="border-2 border-brutal-black p-3 bg-neutral-50 dark:bg-zinc-900">
            <div className="text-neutral-500 uppercase">{t('settings.service.status')}</div>
            <div className="font-bold mt-1">{stateLabel}</div>
          </div>
          <div className="border-2 border-brutal-black p-3 bg-neutral-50 dark:bg-zinc-900">
            <div className="text-neutral-500 uppercase">{t('settings.service.uptime')}</div>
            <div className="font-bold mt-1">{formatUptime(status?.uptime_seconds ?? null)}</div>
          </div>
          <div className="border-2 border-brutal-black p-3 bg-neutral-50 dark:bg-zinc-900">
            <div className="text-neutral-500 uppercase">{t('settings.service.memory')}</div>
            <div className="font-bold mt-1">{memory}</div>
          </div>
          <div className="border-2 border-brutal-black p-3 bg-neutral-50 dark:bg-zinc-900">
            <div className="text-neutral-500 uppercase">PID</div>
            <div className="font-bold mt-1">{status?.pid ?? '—'}</div>
          </div>
        </div>

        {status?.port && (
          <p className="mt-4 text-xs font-mono text-neutral-500">
            127.0.0.1:{status.port} · v{status.version ?? '—'}
          </p>
        )}

        {error && (
          <div className="mt-4 border-2 border-brutal-black bg-red-100 dark:bg-red-950 p-3 text-sm font-mono text-red-800 dark:text-red-200">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-3 mt-6">
          <BrutalButton
            variant="warning"
            disabled={busy || !status?.installed}
            onClick={() => void restart()}
          >
            {t('settings.service.restart')}
          </BrutalButton>
          <BrutalButton disabled={busy} onClick={() => void copyLogPath()}>
            {t('settings.service.copyLogPath')}
          </BrutalButton>
          <BrutalButton disabled={busy} onClick={() => void refresh()}>
            {t('settings.service.refresh')}
          </BrutalButton>
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
