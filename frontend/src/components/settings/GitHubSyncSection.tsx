import React, { useCallback, useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  fetchGitHubAuthStatus,
  fetchSyncAheadBehind,
  fetchSyncQuickstartInfo,
  fetchSyncStatus,
  githubSyncPull,
  githubSyncPush,
  logoutGitHub,
  pollGitHubAuth,
  runSync,
  runSyncQuickstart,
  saveSyncAutoConfig,
  saveSyncProfile,
  startGitHubAuth,
  SyncProfile,
  SyncStatus,
} from '../../lib/dataApi';
import { ShibbolethPanel } from './ShibbolethPanel';
import { SettingsCard, SectionCardHeader } from './SettingsCard';

type NotificationHandler = (text: string, isError: boolean) => void;

type DeviceFlowPhase = 'idle' | 'polling' | 'expired' | 'denied';

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function _relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface GitHubSyncSectionProps {
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
  onNotify: NotificationHandler;
  onSyncComplete?: () => void;
}

function ActionBtn({
  children,
  onClick,
  disabled,
  title,
  primary,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
  primary?: boolean;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`flex items-center gap-1.5 px-3 py-2 border-l-2 border-brutal-black font-bold uppercase text-xs disabled:opacity-40 hover:brightness-95 dark:hover:brightness-125 transition-all ${
        primary
          ? 'bg-brutal-blue text-white'
          : 'bg-neutral-50 dark:bg-zinc-900 text-brutal-black dark:text-white'
      }`}
    >
      {children}
    </button>
  );
}

export function GitHubSyncSection({
  busy,
  onBusyChange,
  onNotify,
  onSyncComplete,
}: GitHubSyncSectionProps): React.ReactElement {
  const { t } = useI18n();

  const openExternal = useCallback(async (url: string) => {
    try {
      if (window.__TAURI__) {
        const { open } = await import('@tauri-apps/plugin-shell');
        await open(url);
      } else {
        window.open(url, '_blank', 'noopener,noreferrer');
      }
    } catch {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }, []);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [repoName, setRepoName] = useState('suzent-brain');
  const [repoPath, setRepoPath] = useState('');
  const [branch, setBranch] = useState('main');
  const [remote, setRemote] = useState('origin');
  const [autoSync, setAutoSync] = useState(true);
  const [intervalHours, setIntervalHours] = useState(4);
  const [autoResolve, setAutoResolve] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [githubAuthenticated, setGithubAuthenticated] = useState(false);
  const [githubUsername, setGithubUsername] = useState<string | null>(null);
  const [githubTokenExpired, setGithubTokenExpired] = useState(false);
  const [linkedRepo, setLinkedRepo] = useState<string | null>(null);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [ahead, setAhead] = useState<number | null>(null);
  const [behind, setBehind] = useState<number | null>(null);

  const [devicePhase, setDevicePhase] = useState<DeviceFlowPhase>('idle');
  const [deviceCode, setDeviceCode] = useState('');
  const [deviceUrl, setDeviceUrl] = useState('');
  const [deviceSessionId, setDeviceSessionId] = useState('');
  const [deviceInterval, setDeviceInterval] = useState(5);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    refresh().catch(() => setSyncStatus(null));
    Promise.all([fetchSyncQuickstartInfo(), fetchGitHubAuthStatus()])
      .then(([info, authStatus]) => {
        setRepoPath((current) => current || info.default_repo_path);
        if (!repoName) setRepoName(info.default_repo_name || 'suzent-brain');
        setGithubAuthenticated(authStatus.authenticated);
        setGithubUsername(authStatus.username ?? null);
        setGithubTokenExpired(authStatus.token_expired ?? false);
      })
      .catch(() => {});
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  async function refresh(): Promise<void> {
    const next = await fetchSyncStatus();
    setSyncStatus(next);
    if (next.profile) applyProfile(next.profile);
    if (next.configured && next.profile) {
      refreshAheadBehind(next.profile.id).catch(() => {});
    }
  }

  async function refreshAheadBehind(profileId?: string): Promise<void> {
    try {
      const counts = await fetchSyncAheadBehind(profileId);
      setAhead(counts.ahead);
      setBehind(counts.behind);
    } catch {
      // network error or repo not yet linked — leave counts null
    }
  }

  async function saveAutoConfig(nextAutoSync: boolean, nextInterval: number): Promise<void> {
    const profileId = syncStatus?.profile?.id;
    if (!profileId) return;
    try {
      await saveSyncAutoConfig(profileId, nextAutoSync, nextInterval, autoResolve);
    } catch {
      // non-critical — ignore
    }
  }

  function applyProfile(profile: SyncProfile): void {
    setRepoPath(profile.repo_path);
    setBranch(profile.branch);
    setRemote(profile.remote);
    setAutoSync(profile.auto_sync_enabled);
    setIntervalHours(profile.interval_hours);
    setAutoResolve(profile.auto_resolve_enabled);
  }

  function requireShibbolethUnlocked(): boolean {
    if (!syncStatus?.requires_shibboleth) return true;
    if (syncStatus.shibboleth_unlocked) return true;
    onNotify(t('settings.data.shibbolethRequiredForSync'), true);
    return false;
  }

  async function handleSignIn(): Promise<void> {
    if (pollTimer.current) clearTimeout(pollTimer.current);
    try {
      const result = await startGitHubAuth();
      setDeviceCode(result.user_code);
      setDeviceUrl(result.verification_uri);
      setDeviceSessionId(result.session_id);
      setDeviceInterval(result.interval);
      setDevicePhase('polling');
      schedulePoll(result.session_id, result.interval);
    } catch (error) {
      onNotify(errMsg(error), true);
    }
  }

  function schedulePoll(sessionId: string, interval: number): void {
    pollTimer.current = setTimeout(() => runPoll(sessionId), interval * 1000);
  }

  async function runPoll(sessionId: string): Promise<void> {
    try {
      const result = await pollGitHubAuth(sessionId);
      if (result.status === 'complete') {
        setDevicePhase('idle');
        setDeviceCode('');
        setGithubAuthenticated(true);
        setGithubUsername(result.username ?? null);
        setGithubTokenExpired(false);
        onNotify(
          t('settings.data.githubSignInDone', { username: result.username ?? '' }),
          false,
        );
      } else if (result.status === 'expired') {
        setDevicePhase('expired');
      } else if (result.status === 'denied') {
        setDevicePhase('denied');
      } else {
        const nextInterval = result.interval ?? deviceInterval;
        setDeviceInterval(nextInterval);
        schedulePoll(sessionId, nextInterval);
      }
    } catch {
      schedulePoll(sessionId, deviceInterval);
    }
  }

  function handleCancelSignIn(): void {
    if (pollTimer.current) clearTimeout(pollTimer.current);
    setDevicePhase('idle');
    setDeviceCode('');
  }

  async function handleSignOut(): Promise<void> {
    try {
      await logoutGitHub();
      setGithubAuthenticated(false);
      setGithubUsername(null);
      setGithubTokenExpired(false);
    } catch (error) {
      onNotify(errMsg(error), true);
    }
  }

  async function handleQuickStart(): Promise<void> {
    if (!githubAuthenticated) {
      onNotify(t('settings.data.githubSignInDesc'), true);
      return;
    }
    onBusyChange(true);
    onNotify(t('settings.data.githubQuickStartRunning'), false);
    try {
      const result = await runSyncQuickstart({
        repo_name: repoName.trim() || 'suzent-brain',
        repo_path: advancedOpen && repoPath.trim() ? repoPath.trim() : undefined,
        branch: branch.trim() || 'main',
        remote: remote.trim() || 'origin',
        auto_sync_enabled: autoSync,
        auto_resolve_enabled: autoResolve,
        interval_hours: intervalHours,
      });
      applyProfile(result.profile);
      setRepoPath(result.repo_path);
      setBranch(result.branch || 'main');
      setLinkedRepo(result.github_repo ?? null);
      setInstallUrl(result.install_required ? (result.install_url ?? null) : null);
      await refresh();
      const summary = result.actions.join(' · ');
      const warn = result.warnings.length ? ` ${result.warnings.join(' ')}` : '';
      onNotify(
        t('settings.data.githubQuickStartDone', {
          repo: result.github_repo || repoName,
          summary,
        }) + warn,
        Boolean(result.warnings.length && !result.git?.valid),
      );
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleSave(): Promise<void> {
    if (!repoPath.trim()) return;
    onBusyChange(true);
    try {
      const profile = await saveSyncProfile({
        ...(syncStatus?.profile || {}),
        repo_path: repoPath.trim(),
        branch: branch.trim() || 'main',
        remote: remote.trim() || 'origin',
        auto_sync_enabled: autoSync,
        interval_hours: intervalHours,
        auto_resolve_enabled: autoResolve,
        encrypted_secret_sync_enabled:
          syncStatus?.profile?.encrypted_secret_sync_enabled ?? false,
      });
      applyProfile(profile);
      if (syncStatus?.profile) {
        await saveSyncAutoConfig(profile.id, autoSync, intervalHours, autoResolve);
      }
      await refresh();
      onNotify(t('settings.data.githubSaved'), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  function makeSyncHandler(
    apiFn: (profileId: string) => Promise<unknown>,
    successKey: string,
    notifyComplete = false,
  ) {
    return async function (): Promise<void> {
      if (!requireShibbolethUnlocked()) return;
      onBusyChange(true);
      try {
        const profile = syncStatus?.profile;
        if (!profile) throw new Error('GitHub sync is not configured.');
        await apiFn(profile.id);
        await refresh();
        onNotify(t(successKey), false);
        if (notifyComplete) onSyncComplete?.();
      } catch (error) {
        onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
      } finally {
        onBusyChange(false);
      }
    };
  }

  const handleSync = makeSyncHandler(runSync, 'settings.data.githubPushed', true);
  const handlePull = makeSyncHandler(githubSyncPull, 'settings.data.githubPulled', true);
  const handlePush = makeSyncHandler(githubSyncPush, 'settings.data.githubPushed');

  const configured = Boolean(syncStatus?.configured && syncStatus.profile);

  return (
    <SettingsCard>
      <SectionCardHeader
        iconTone="green"
        icon={
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2v20M5 7h14M5 17h14" />
          </svg>
        }
        title={t('settings.data.githubTitle')}
        description={
          <>
            {t('settings.data.githubDesc')}
            <div className="flex flex-wrap items-center gap-2 mt-3">
            {configured && (
              <span className="px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase bg-brutal-green">
                {t('settings.data.githubConnected')}
              </span>
            )}
            {githubAuthenticated && (
              <>
                <span className="px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase bg-brutal-blue text-white">
                  {githubUsername
                    ? t('settings.data.githubSignInDone', { username: githubUsername })
                    : t('settings.data.githubSignedIn')}
                </span>
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="px-2 py-1 border-2 border-brutal-black font-bold uppercase text-[10px] bg-white dark:bg-zinc-700 hover:bg-red-50"
                >
                  {t('settings.data.githubSignOut')}
                </button>
              </>
            )}
            </div>
          </>
        }
      />

      {/* GitHub sign-in / device flow */}
      {githubTokenExpired && devicePhase === 'idle' && (
        <div className="mb-3 border-2 border-brutal-black bg-red-50 dark:bg-red-900/20 p-3 flex items-start gap-2">
          <span className="text-red-600 dark:text-red-400 text-xs font-bold uppercase shrink-0">⚠</span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-red-700 dark:text-red-400">GitHub token expired</p>
            <p className="text-[10px] text-red-600 dark:text-red-400 mt-0.5">Sign in again to re-authenticate.</p>
          </div>
        </div>
      )}
      {!githubAuthenticated && devicePhase === 'idle' && (
        <div className="mb-4">
          <button
            type="button"
            disabled={busy}
            onClick={handleSignIn}
            className="w-full px-4 py-3 bg-brutal-black border-2 border-brutal-black font-black uppercase text-sm text-white shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 disabled:opacity-50"
          >
            {t('settings.data.githubSignInButton')}
          </button>
        </div>
      )}

      {devicePhase === 'polling' && (
        <div className="mb-4 border-2 border-brutal-black bg-brutal-blue/10 p-4 space-y-3">
          <p className="text-xs font-bold uppercase text-neutral-700 dark:text-neutral-300">
            {t('settings.data.githubSignInDesc')}
          </p>
          <span className="inline-flex w-full font-mono text-2xl font-black tracking-[0.22em] border-4 border-brutal-black px-3 py-2 dark:text-white select-all justify-center bg-white dark:bg-zinc-900">
            {deviceCode}
          </span>
          <button
            type="button"
            onClick={() => void openExternal(deviceUrl)}
            className="w-full px-4 py-2 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 text-left flex items-center justify-between"
          >
            <span className="font-mono text-[11px] truncate">{deviceUrl}</span>
            <span className="ml-2 shrink-0">↗</span>
          </button>
          <p className="text-[10px] text-neutral-500 dark:text-neutral-400 uppercase font-bold animate-pulse text-center">
            {t('settings.data.githubSignInWaiting')}
          </p>
          <button
            type="button"
            onClick={handleCancelSignIn}
            className="w-full px-3 py-2 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700"
          >
            Cancel
          </button>
        </div>
      )}

      {(devicePhase === 'expired' || devicePhase === 'denied') && (
        <div className="mb-4 border-2 border-brutal-black bg-red-50 dark:bg-red-900/20 p-4 space-y-3">
          <p className="text-xs font-bold text-red-700 dark:text-red-400">
            {devicePhase === 'expired'
              ? t('settings.data.githubSignInExpired')
              : t('settings.data.githubSignInDenied')}
          </p>
          <button
            type="button"
            onClick={() => { setDevicePhase('idle'); setDeviceCode(''); }}
            className="px-3 py-2 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700"
          >
            {t('settings.data.githubSignInButton')}
          </button>
        </div>
      )}

      {/* App install required banner */}
      {installUrl && (
        <div className="mb-4 border-2 border-brutal-yellow bg-brutal-yellow/20 p-4 space-y-2">
          <p className="text-xs font-bold uppercase">GitHub App installation required</p>
          <p className="text-xs text-neutral-700 dark:text-neutral-300">
            The Suzent GitHub App needs to be installed on your account before it can create repositories.
          </p>
          <button
            type="button"
            onClick={() => void openExternal(installUrl)}
            className="inline-block px-4 py-2 bg-brutal-black border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110"
          >
            Install Suzent on GitHub →
          </button>
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
            After installing, click Quick start again.
          </p>
        </div>
      )}

      {/* Action bar */}
      <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 flex items-stretch">
        {/* Repo name / input */}
        <div className="flex-1 flex items-center px-3 py-2 min-w-0">
          {configured ? (
            <span className="font-mono text-xs truncate text-neutral-600 dark:text-neutral-400">
              {linkedRepo ?? repoName}
            </span>
          ) : (
            <input
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              placeholder="suzent-brain"
              title={t('settings.data.githubRepoNameHint')}
              className="w-full bg-transparent font-mono text-xs focus:outline-none dark:text-white placeholder:text-neutral-400"
            />
          )}
        </div>

        <div className="w-px bg-brutal-black/20 dark:bg-white/10" />

        {configured ? (
          <>
            {/* Pull button */}
            <ActionBtn onClick={handlePull} disabled={busy} title="Pull from remote (overwrite local)">
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 2v9M5 8l3 3 3-3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2 13h12" />
              </svg>
              <span className="text-xs font-bold uppercase">
                {behind !== null && behind > 0 ? `Pull (${behind})` : 'Pull'}
              </span>
            </ActionBtn>
            {/* Push button */}
            <ActionBtn onClick={handlePush} disabled={busy} title="Push to remote (overwrite remote)">
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 14V5M5 8L8 5l3 3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2 3h12" />
              </svg>
              <span className="text-xs font-bold uppercase">
                {ahead !== null && ahead > 0 ? `Push (${ahead})` : 'Push'}
              </span>
            </ActionBtn>
            {/* Sync button */}
            <ActionBtn onClick={handleSync} disabled={busy} title="Sync (pull then push)">
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M1 8a7 7 0 1 0 14 0A7 7 0 0 0 1 8z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 6l3-3 3 3M11 10l-3 3-3-3" />
              </svg>
              <span className="text-xs font-bold uppercase">Sync</span>
            </ActionBtn>
          </>
        ) : (
          <ActionBtn onClick={handleQuickStart} disabled={busy || !githubAuthenticated} title={t('settings.data.githubQuickStartButton')} primary>
            {busy
              ? <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" d="M8 2a6 6 0 1 1-4.243 1.757" /></svg>
              : <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M13 8A5 5 0 1 1 8 3" /><path strokeLinecap="round" strokeLinejoin="round" d="M13 3v4h-4" /></svg>
            }
            <span className="text-xs font-bold uppercase">{busy ? t('settings.data.working') : t('settings.data.githubQuickStartButton')}</span>
          </ActionBtn>
        )}
      </div>

      {/* Status line below action bar */}
      {configured && (
        <div className="px-1 mt-1">
          <span className="text-[10px] text-neutral-400 dark:text-neutral-500">
            {syncStatus?.profile?.last_sync_at
              ? `Last synced ${_relativeTime(syncStatus.profile.last_sync_at)}`
              : 'Never synced'}
          </span>
        </div>
      )}

      <button
        type="button"
        onClick={() => setAdvancedOpen((open) => !open)}
        className="mt-4 w-full flex items-center justify-between border-2 border-brutal-black px-3 py-2 text-xs font-bold uppercase bg-neutral-50 dark:bg-zinc-900"
      >
        {t('settings.data.githubAdvanced')}
        <span>{advancedOpen ? '−' : '+'}</span>
      </button>

      {advancedOpen && (
        <div className="mt-3 space-y-4 border-2 border-brutal-black border-dashed p-4">
          <div className="block text-xs font-bold uppercase">
            {t('settings.data.githubRepoPlaceholder')}
            <p className="mt-1 w-full bg-neutral-100 dark:bg-zinc-800 border-2 border-brutal-black/30 px-3 py-2 font-mono text-xs dark:text-neutral-400 text-neutral-500 select-all">{repoPath || '—'}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="block text-xs font-bold uppercase">
              {t('settings.data.githubBranch')}
              <p className="mt-1 w-full bg-neutral-100 dark:bg-zinc-800 border-2 border-brutal-black/30 px-3 py-2 font-mono text-xs dark:text-neutral-400 text-neutral-500">{branch || 'main'}</p>
            </div>
            <div className="block text-xs font-bold uppercase">
              {t('settings.data.githubRemote')}
              <p className="mt-1 w-full bg-neutral-100 dark:bg-zinc-800 border-2 border-brutal-black/30 px-3 py-2 font-mono text-xs dark:text-neutral-400 text-neutral-500">{remote || 'origin'}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-xs font-bold uppercase">
              <input type="checkbox" checked={autoSync} onChange={(e) => { setAutoSync(e.target.checked); void saveAutoConfig(e.target.checked, intervalHours); }} />
              Auto-sync every
            </label>
            <label className="flex items-center gap-2 text-xs font-bold uppercase">
              <input type="number" min={1} value={intervalHours} onChange={(e) => { const v = Number(e.target.value) || 4; setIntervalHours(v); void saveAutoConfig(autoSync, v); }} className="w-16 bg-white dark:bg-zinc-800 border-2 border-brutal-black px-2 py-1" />
              hours
            </label>
          </div>
          <ShibbolethPanel profile={syncStatus?.profile} syncStatus={syncStatus} busy={busy} onBusyChange={onBusyChange} onNotify={onNotify} onChanged={refresh} />
          {syncStatus?.profile?.last_revision !== undefined && (
            <p className="font-mono text-xs text-neutral-500 dark:text-neutral-400">
              {t('settings.data.githubLastRevision')}: {syncStatus.profile.last_revision || t('settings.data.githubNone')}
            </p>
          )}
        </div>
      )}
    </SettingsCard>
  );
}
