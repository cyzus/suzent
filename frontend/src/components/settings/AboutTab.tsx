import React, { useCallback, useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import { fetchSystemVersion } from '../../lib/api';
import {
  checkDesktopUpdate,
  startDesktopUpdateAndRestart,
  type UpdateStatus,
} from '../../lib/desktopUpdates';
import { SuzentLogo } from '../SuzentLogo';
import { SettingsCard } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

type BackendVersionState =
  | { status: 'loading'; version: null }
  | { status: 'ready'; version: string }
  | { status: 'unavailable'; version: null };

export function AboutTab(): React.ReactElement {
  const { t } = useI18n();
  const [backend, setBackend] = useState<BackendVersionState>({
    status: 'loading',
    version: null,
  });
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [startingUpdate, setStartingUpdate] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const refreshUpdateStatus = useCallback(async (force = false): Promise<void> => {
    setCheckingUpdate(true);
    setUpdateError(null);
    try {
      const status = await checkDesktopUpdate(force);
      setUpdateStatus(status);
      if (status.error) {
        setUpdateError(t('updates.checkFailed', { error: status.error }));
      }
    } catch (error) {
      setUpdateStatus(null);
      const message = error instanceof Error ? error.message : String(error);
      setUpdateError(t('updates.checkFailed', { error: message }));
    } finally {
      setCheckingUpdate(false);
    }
  }, [t]);

  useEffect(() => {
    let active = true;

    fetchSystemVersion()
      .then(({ backendVersion }) => {
        if (active) setBackend({ status: 'ready', version: backendVersion });
      })
      .catch(() => {
        if (active) setBackend({ status: 'unavailable', version: null });
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    void refreshUpdateStatus();
  }, [refreshUpdateStatus]);

  async function handleUpdate(): Promise<void> {
    const latest = updateStatus?.latest_version || t('updates.latestVersion');
    if (!window.confirm(t('updates.confirmRestart', { version: latest }))) return;

    setStartingUpdate(true);
    setUpdateError(null);
    try {
      await startDesktopUpdateAndRestart();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setUpdateError(t('updates.startFailed', { error: message }));
      setStartingUpdate(false);
    }
  }

  const backendVersion = backend.status === 'loading'
    ? t('common.loading')
    : backend.version && backend.version !== 'unknown'
      ? `v${backend.version}`
      : t('settings.about.unavailable');
  const frontendVersion = __FRONTEND_VERSION__ === 'unknown'
    ? t('settings.about.unavailable')
    : `v${__FRONTEND_VERSION__}`;

  return (
    <div className="space-y-6">
      <SettingsHeader
        title={t('settings.about.title')}
        subtitle={t('settings.about.subtitle')}
      />

      <SettingsCard className="overflow-hidden">
        <div className="flex flex-col items-center text-center py-4">
          <SuzentLogo className="w-20 h-20" interactive />
          <h2 className="mt-5 text-3xl font-black uppercase tracking-tight">Suzent</h2>
          <p className="mt-2 max-w-xl text-sm text-neutral-600 dark:text-neutral-400">
            {t('settings.about.description')}
          </p>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <VersionCard
            label={t('settings.about.frontendVersion')}
            value={frontendVersion}
            tone="yellow"
          />
          <VersionCard
            label={t('settings.about.backendVersion')}
            value={backendVersion}
            tone={backend.status === 'unavailable' ? 'red' : 'blue'}
          />
        </div>

        <div className="mt-6 border-t-3 border-brutal-black pt-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-black uppercase">{t('updates.sectionTitle')}</h3>
              <p className={`mt-1 text-sm ${
                updateError
                  ? 'text-brutal-red'
                  : 'text-neutral-600 dark:text-neutral-400'
              }`}>
                {checkingUpdate
                  ? t('updates.checking')
                  : updateError
                    ? updateError
                    : updateStatus?.update_available
                      ? t('updates.availableTitle', {
                          version: updateStatus.latest_version || t('updates.latestVersion'),
                        })
                      : updateStatus
                        ? t('updates.upToDate')
                        : t('updates.checkDescription')}
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void refreshUpdateStatus(true)}
                disabled={checkingUpdate || startingUpdate}
                className="border-2 border-brutal-black bg-white px-4 py-2 text-sm font-black uppercase text-brutal-black shadow-brutal-sm brutal-btn disabled:cursor-wait disabled:opacity-50"
              >
                {checkingUpdate ? t('updates.checking') : t('updates.check')}
              </button>

              {updateStatus?.update_available && (
                <button
                  type="button"
                  onClick={() => void handleUpdate()}
                  disabled={startingUpdate}
                  className="border-2 border-brutal-black bg-brutal-blue px-4 py-2 text-sm font-black uppercase text-white shadow-brutal-sm brutal-btn disabled:cursor-wait disabled:opacity-50"
                >
                  {startingUpdate ? t('updates.starting') : t('updates.updateNow')}
                </button>
              )}
            </div>
          </div>
        </div>
      </SettingsCard>
    </div>
  );
}

interface VersionCardProps {
  label: string;
  value: string;
  tone: 'yellow' | 'blue' | 'red';
}

function VersionCard({ label, value, tone }: VersionCardProps): React.ReactElement {
  const toneClass = {
    yellow: 'bg-brutal-yellow text-brutal-black',
    blue: 'bg-brutal-blue text-white',
    red: 'bg-brutal-red text-white',
  }[tone];

  return (
    <div className="border-3 border-brutal-black bg-neutral-50 dark:bg-zinc-900 shadow-brutal-sm">
      <div className={`border-b-3 border-brutal-black px-4 py-2 text-xs font-black uppercase ${toneClass}`}>
        {label}
      </div>
      <div className="px-4 py-5 font-mono text-2xl font-bold">
        {value}
      </div>
    </div>
  );
}
