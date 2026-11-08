import { BrutalButton } from '../BrutalButton';
import React, { useCallback, useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import { fetchSystemVersion, shortCommit } from '../../lib/api';
import { formatRelativeTime } from '../../lib/chatUtils';
import {
  commitUrl,
  fetchDesktopAbout,
  releaseNotesUrl,
  shortInstallationId,
  type DesktopAbout,
} from '../../lib/desktopAbout';
import {
  checkDesktopUpdate,
  getAutoUpdateEnabled,
  setAutoUpdateEnabled,
  startDesktopUpdateAndRestart,
  type UpdateStatus,
} from '../../lib/desktopUpdates';
import { isWeb } from '../../lib/runtime';
import { SuzentLogo } from '../SuzentLogo';
import { SettingsCard, SettingsPage } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

type BackendVersionState = {
  status: 'loading' | 'ready' | 'unavailable';
  version: string | null;
  /** Full commit for links; display uses shortCommit. */
  commit: string | null;
  developmentMode: boolean;
  buildSource: string | null;
  runtime: string | null;
  installationId: string | null;
  dataDir: string | null;
};

function formatVersion(value: string | null | undefined, unavailable: string): string {
  if (!value || value === 'unknown') return unavailable;
  return value.startsWith('v') ? value : `v${value}`;
}

async function openExternal(url: string): Promise<void> {
  if (window.__TAURI__) {
    const { open } = await import('@tauri-apps/plugin-shell');
    await open(url);
  } else {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

export function AboutTab(): React.ReactElement {
  const { t, locale } = useI18n();
  const [backend, setBackend] = useState<BackendVersionState>({
    status: 'loading',
    version: null,
    commit: null,
    developmentMode: false,
    buildSource: null,
    runtime: null,
    installationId: null,
    dataDir: null,
  });
  const [desktop, setDesktop] = useState<DesktopAbout | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [startingUpdate, setStartingUpdate] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [autoUpdate, setAutoUpdate] = useState<boolean | null>(null);

  useEffect(() => {
    if (isWeb()) return;
    let active = true;
    getAutoUpdateEnabled()
      .then((enabled) => {
        if (active) setAutoUpdate(enabled);
      })
      .catch(() => {
        if (active) setAutoUpdate(null);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    fetchDesktopAbout()
      .then((about) => {
        if (active) setDesktop(about);
      })
      .catch(() => {
        if (active) setDesktop(null);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleAutoUpdateChange(enabled: boolean): Promise<void> {
    setAutoUpdate(enabled);
    try {
      await setAutoUpdateEnabled(enabled);
    } catch (error) {
      setAutoUpdate(!enabled);
      const message = error instanceof Error ? error.message : String(error);
      setUpdateError(t('updates.autoUpdateFailed', { error: message }));
    }
  }

  const refreshUpdateStatus = useCallback(
    async (force = false): Promise<void> => {
      setCheckingUpdate(true);
      setUpdateError(null);
      try {
        const status = await checkDesktopUpdate(force);
        setUpdateStatus(status);
        setLastCheckedAt(new Date().toISOString());
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
    },
    [t]
  );

  useEffect(() => {
    let active = true;

    fetchSystemVersion()
      .then((payload) => {
        if (!active) return;
        setBackend({
          status: 'ready',
          version: payload.backendVersion,
          commit: payload.buildCommit !== 'unknown' ? payload.buildCommit : null,
          developmentMode: payload.developmentMode,
          buildSource: payload.buildSource ?? null,
          runtime: payload.runtime ?? null,
          installationId: payload.installationId ?? null,
          dataDir: payload.dataDir ?? null,
        });
      })
      .catch(() => {
        if (active) {
          setBackend({
            status: 'unavailable',
            version: null,
            commit: null,
            developmentMode: false,
            buildSource: null,
            runtime: null,
            installationId: null,
            dataDir: null,
          });
        }
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

  const unavailable = t('settings.about.unavailable');
  const frontendVersion = formatVersion(__FRONTEND_VERSION__, unavailable);
  const deviceVersion = formatVersion(desktop?.appVersion || __FRONTEND_VERSION__, unavailable);
  const backendVersion =
    backend.status === 'loading'
      ? t('common.loading')
      : formatVersion(backend.version, unavailable);
  const productVersion = frontendVersion !== unavailable ? frontendVersion : backendVersion;
  const commit = shortCommit(__FRONTEND_BUILD_COMMIT__) || shortCommit(backend.commit) || null;
  const fullCommit =
    (__FRONTEND_BUILD_COMMIT__ !== 'unknown' && __FRONTEND_BUILD_COMMIT__) ||
    backend.commit ||
    null;

  const buildSourceKey = backend.buildSource || 'unknown';
  const buildSourceLabel =
    buildSourceKey === 'ci'
      ? t('settings.about.buildSourceCi', { version: productVersion })
      : buildSourceKey === 'development'
        ? t('settings.about.buildSourceDevelopment')
        : buildSourceKey === 'source'
          ? t('settings.about.buildSourceSource')
          : unavailable;

  const distributionKey = desktop?.distribution || (isWeb() ? 'web' : 'github');
  const distributionLabel =
    distributionKey === 'microsoft_store'
      ? t('settings.about.distributionStore')
      : distributionKey === 'development'
        ? t('settings.about.distributionDevelopment')
        : distributionKey === 'web'
          ? t('settings.about.distributionWeb')
          : t('settings.about.distributionGithub');

  const runtimeKey = desktop?.runtime || backend.runtime || 'unknown';
  const runtimeLabel =
    runtimeKey === 'bundled'
      ? t('settings.about.runtimeBundled')
      : runtimeKey === 'source'
        ? t('settings.about.runtimeSource')
        : runtimeKey === 'installed'
          ? t('settings.about.runtimeInstalled')
          : unavailable;

  const installPath = desktop?.installPath || desktop?.dataDir || backend.dataDir;
  const installationId = shortInstallationId(backend.installationId);
  const installationValue =
    installationId && installPath
      ? `${installationId} (${installPath})`
      : installationId || installPath || unavailable;

  const lastCheckedLabel = lastCheckedAt
    ? t('settings.about.lastChecked', {
        time: formatRelativeTime(lastCheckedAt, locale) || t('settings.about.justNow'),
      })
    : null;

  const updateTitle = checkingUpdate
    ? t('updates.checking')
    : updateError
      ? t('updates.checkFailedShort')
      : updateStatus?.update_available
        ? t('updates.availableTitle', {
            version: updateStatus.latest_version || t('updates.latestVersion'),
          })
        : updateStatus
          ? t('updates.upToDate')
          : t('updates.checkDescription');

  const updateTone: 'green' | 'blue' | 'red' | 'neutral' = checkingUpdate
    ? 'neutral'
    : updateError
      ? 'red'
      : updateStatus?.update_available
        ? 'blue'
        : updateStatus
          ? 'green'
          : 'neutral';

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.about.title')} />
      <div>
        <BrutalButton
          variant="ghost"
          size="sm"
          onClick={() => {
            window.location.hash = '#/setup';
          }}
        >
          {t('onboarding.restart')}
        </BrutalButton>
      </div>

      <SettingsCard className="overflow-hidden">
        <div className="flex flex-col items-center text-center py-4">
          <SuzentLogo className="w-20 h-20" interactive />
          <h2 className="mt-5 text-3xl font-black uppercase tracking-tight">Suzent</h2>
          <p className="mt-2 max-w-xl text-sm text-neutral-600 dark:text-neutral-400">
            {t('settings.about.description')}
          </p>
        </div>

        <div className="mt-6 border-t-3 border-brutal-black pt-6">
          <div
            className={`flex flex-col gap-4 border-2 border-brutal-black p-4 shadow-brutal-sm sm:flex-row sm:items-center sm:justify-between ${
              updateTone === 'green'
                ? 'bg-emerald-50 dark:bg-emerald-950/30'
                : updateTone === 'blue'
                  ? 'bg-sky-50 dark:bg-sky-950/30'
                  : updateTone === 'red'
                    ? 'bg-red-50 dark:bg-red-950/30'
                    : 'bg-neutral-50 dark:bg-zinc-900'
            }`}
          >
            <div className="flex min-w-0 items-start gap-3">
              <UpdateStatusIcon tone={updateTone} />
              <div className="min-w-0">
                <h3 className="font-black uppercase leading-tight">{updateTitle}</h3>
                {updateError ? (
                  <p className="mt-1 text-sm text-brutal-red">{updateError}</p>
                ) : (
                  lastCheckedLabel && (
                    <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                      {lastCheckedLabel}
                    </p>
                  )
                )}
              </div>
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

              <button
                type="button"
                onClick={() => void openExternal(releaseNotesUrl(productVersion))}
                className="border-2 border-brutal-black bg-white px-4 py-2 text-sm font-black uppercase text-brutal-black shadow-brutal-sm brutal-btn"
              >
                {t('settings.about.releaseNotes')}
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

          {autoUpdate !== null && (
            <label className="mt-5 flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={autoUpdate}
                onChange={(e) => void handleAutoUpdateChange(e.target.checked)}
                className="mt-0.5 h-5 w-5 border-2 border-brutal-black accent-brutal-black"
              />
              <span>
                <span className="block text-xs font-bold uppercase">{t('updates.autoUpdate')}</span>
                <span className="mt-1 block text-sm text-neutral-600 dark:text-neutral-400">
                  {t('updates.autoUpdateDescription')}
                </span>
              </span>
            </label>
          )}
        </div>

        <dl className="mt-6 border-t-3 border-brutal-black pt-2">
          <AboutDetailRow label={t('settings.about.version')} value={productVersion} />
          <AboutDetailRow label={t('settings.about.thisDevice')} value={deviceVersion} />
          <AboutDetailRow
            label={t('settings.about.connectedBackend')}
            value={backendVersion}
            badge={backend.developmentMode ? t('settings.about.developmentBuild') : null}
          />
          <AboutDetailRow
            label={t('settings.about.commit')}
            value={
              commit && fullCommit ? (
                <button
                  type="button"
                  onClick={() => void openExternal(commitUrl(fullCommit))}
                  className="font-mono text-sm font-bold text-brutal-blue underline-offset-2 hover:underline"
                >
                  {commit}
                </button>
              ) : (
                unavailable
              )
            }
          />
          <AboutDetailRow label={t('settings.about.buildSource')} value={buildSourceLabel} />
          <AboutDetailRow label={t('settings.about.distribution')} value={distributionLabel} />
          <AboutDetailRow label={t('settings.about.runtime')} value={runtimeLabel} />
          <AboutDetailRow
            label={t('settings.about.installationId')}
            value={<span className="break-all font-mono text-sm">{installationValue}</span>}
          />
        </dl>
      </SettingsCard>
    </SettingsPage>
  );
}

function UpdateStatusIcon({
  tone,
}: {
  tone: 'green' | 'blue' | 'red' | 'neutral';
}): React.ReactElement {
  const className =
    tone === 'green'
      ? 'bg-brutal-green text-brutal-black'
      : tone === 'blue'
        ? 'bg-brutal-blue text-white'
        : tone === 'red'
          ? 'bg-brutal-red text-white'
          : 'bg-neutral-200 text-brutal-black dark:bg-zinc-700 dark:text-white';
  return (
    <div
      className={`flex h-10 w-10 shrink-0 items-center justify-center border-2 border-brutal-black shadow-brutal-sm ${className}`}
      aria-hidden
    >
      {tone === 'green' ? (
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M16.704 5.29a1 1 0 0 1 .006 1.414l-7.25 7.333a1 1 0 0 1-1.432.01L3.29 9.78a1 1 0 1 1 1.42-1.408l3.58 3.612 6.54-6.614a1 1 0 0 1 1.414-.006Z"
            clipRule="evenodd"
          />
        </svg>
      ) : tone === 'blue' ? (
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor">
          <path d="M10 3a1 1 0 0 1 1 1v4.586l1.293-1.293a1 1 0 1 1 1.414 1.414l-3 3a1 1 0 0 1-1.414 0l-3-3A1 1 0 0 1 7.707 7.293L9 8.586V4a1 1 0 0 1 1-1Z" />
          <path d="M4 12a1 1 0 0 1 1 1v1h10v-1a1 1 0 1 1 2 0v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1Z" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm-.75-4.75a.75.75 0 0 0 1.5 0v-5a.75.75 0 0 0-1.5 0v5Zm.75 3.25a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
            clipRule="evenodd"
          />
        </svg>
      )}
    </div>
  );
}

interface AboutDetailRowProps {
  label: string;
  value: React.ReactNode;
  badge?: string | null;
}

export function AboutDetailRow({ label, value, badge }: AboutDetailRowProps): React.ReactElement {
  return (
    <div className="grid gap-1 border-b-2 border-brutal-black/10 py-3 last:border-b-0 sm:grid-cols-[11rem_minmax(0,1fr)] sm:items-start sm:gap-4">
      <dt className="text-xs font-black uppercase text-neutral-500 dark:text-neutral-400">
        {label}
      </dt>
      <dd className="min-w-0 text-sm font-semibold text-brutal-black dark:text-white">
        <div className="flex flex-wrap items-center gap-2">
          <span>{value}</span>
          {badge && (
            <span className="inline-block border-2 border-brutal-black bg-neutral-200 px-2 py-0.5 text-[10px] font-black uppercase text-brutal-black dark:bg-zinc-700 dark:text-white">
              {badge}
            </span>
          )}
        </div>
      </dd>
    </div>
  );
}
