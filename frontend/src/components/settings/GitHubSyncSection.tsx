import React, { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  fetchGitHubAuthStatus,
  fetchSyncQuickstartInfo,
  fetchSyncStatus,
  githubSyncPull,
  githubSyncPush,
  logoutGitHub,
  pollGitHubAuth,
  runSyncQuickstart,
  saveSyncAutoConfig,
  saveSyncProfile,
  startGitHubAuth,
  SyncProfile,
  SyncStatus,
  validateGitHubSync,
} from '../../lib/dataApi';
import { ShibbolethPanel } from './ShibbolethPanel';

type NotificationHandler = (text: string, isError: boolean) => void;

type DeviceFlowPhase = 'idle' | 'polling' | 'expired' | 'denied';

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

interface GitHubSyncSectionProps {
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
  onNotify: NotificationHandler;
}

export function GitHubSyncSection({
  busy,
  onBusyChange,
  onNotify,
}: GitHubSyncSectionProps): React.ReactElement {
  const { t } = useI18n();
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [repoName, setRepoName] = useState('suzent-brain');
  const [repoPath, setRepoPath] = useState('');
  const [branch, setBranch] = useState('main');
  const [remote, setRemote] = useState('origin');
  const [autoSync, setAutoSync] = useState(false);
  const [intervalHours, setIntervalHours] = useState(4);
  const [autoResolve, setAutoResolve] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [githubAuthenticated, setGithubAuthenticated] = useState(false);
  const [githubUsername, setGithubUsername] = useState<string | null>(null);
  const [linkedRepo, setLinkedRepo] = useState<string | null>(null);
  const [installUrl, setInstallUrl] = useState<string | null>(null);

  const [devicePhase, setDevicePhase] = useState<DeviceFlowPhase>('idle');
  const [deviceCode, setDeviceCode] = useState('');
  const [deviceUrl, setDeviceUrl] = useState('');
  const [deviceSessionId, setDeviceSessionId] = useState('');
  const [deviceInterval, setDeviceInterval] = useState(5);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    refresh().catch(() => setSyncStatus(null));
    fetchSyncQuickstartInfo()
      .then((info) => {
        setGithubAuthenticated(info.github_authenticated ?? false);
        setRepoPath((current) => current || info.default_repo_path);
        if (!repoName) setRepoName(info.default_repo_name || 'suzent-brain');
      })
      .catch(() => {});
    fetchGitHubAuthStatus()
      .then((status) => {
        setGithubAuthenticated(status.authenticated);
        setGithubUsername(status.username);
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

  async function handleSaveProfile(): Promise<void> {
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
      await refresh();
      onNotify(t('settings.data.githubSaved'), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleValidate(): Promise<void> {
    if (!repoPath.trim()) return;
    onBusyChange(true);
    try {
      await validateGitHubSync({
        repo_path: repoPath.trim(),
        branch: branch.trim() || 'main',
        remote: remote.trim() || 'origin',
      });
      await refresh();
      onNotify(t('settings.data.githubValid'), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handlePush(): Promise<void> {
    if (!requireShibbolethUnlocked()) return;
    onBusyChange(true);
    try {
      const profile =
        syncStatus?.profile ||
        (await saveSyncProfile({
          repo_path: repoPath.trim(),
          branch: branch.trim() || 'main',
          remote: remote.trim() || 'origin',
        }));
      await githubSyncPush(profile.id);
      await refresh();
      onNotify(t('settings.data.githubPushed'), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handlePull(): Promise<void> {
    if (!requireShibbolethUnlocked()) return;
    onBusyChange(true);
    try {
      const profile = syncStatus?.profile;
      if (!profile) throw new Error('GitHub sync is not configured.');
      const confirmed = window.confirm(t('settings.data.githubPullConfirm'));
      if (!confirmed) return;
      await githubSyncPull(profile.id);
      await refresh();
      onNotify(t('settings.data.githubPulled'), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleSaveAutomation(): Promise<void> {
    const profile = syncStatus?.profile;
    if (!profile) return;
    onBusyChange(true);
    try {
      const updated = await saveSyncAutoConfig(
        profile.id,
        autoSync,
        intervalHours,
        autoResolve,
      );
      applyProfile(updated);
      onNotify(t('settings.data.githubSaved'), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  const configured = Boolean(syncStatus?.configured && syncStatus.profile);

  return (
    <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
      <div className="flex items-start gap-4 mb-6">
        <div className="w-12 h-12 bg-brutal-green border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-brutal-black">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2v20M5 7h14M5 17h14" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-xl font-bold uppercase">{t('settings.data.githubTitle')}</h3>
          <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.data.githubDesc')}</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {configured && (
              <span className="px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase bg-brutal-green">
                {t('settings.data.githubConnected')}
              </span>
            )}
            {githubAuthenticated && (
              <span className="px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase bg-brutal-blue text-white">
                {githubUsername
                  ? t('settings.data.githubSignInDone', { username: githubUsername })
                  : t('settings.data.githubSignedIn')}
              </span>
            )}
            {linkedRepo && (
              <span className="px-2 py-1 border-2 border-brutal-black text-[10px] font-mono bg-neutral-100 dark:bg-zinc-900">
                {linkedRepo}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* GitHub sign-in / device flow */}
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
          <p className="text-xs font-bold uppercase">
            {t('settings.data.githubSignInCode', { url: deviceUrl })}
          </p>
          <p className="font-mono text-2xl font-black tracking-widest text-center border-2 border-brutal-black py-3 bg-white dark:bg-zinc-900">
            {deviceCode}
          </p>
          <p className="text-xs text-neutral-600 dark:text-neutral-400 text-center">
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

      {githubAuthenticated && (
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={handleSignOut}
            className="px-3 py-1 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700 hover:bg-red-50"
          >
            {t('settings.data.githubSignOut')}
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
          <a
            href={installUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-4 py-2 bg-brutal-black border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110"
          >
            Install Suzent on GitHub →
          </a>
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
            After installing, click Quick start again.
          </p>
        </div>
      )}

      {/* Quick start */}
      <div className="border-2 border-brutal-black bg-brutal-blue/10 p-4 space-y-4">
        <label className="block text-xs font-bold uppercase">
          {t('settings.data.githubRepoNameLabel')}
          <input
            value={repoName}
            onChange={(event) => setRepoName(event.target.value)}
            placeholder="suzent-brain"
            className="mt-1 w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-sm focus:outline-none dark:text-white"
          />
        </label>
        <p className="text-[11px] text-neutral-600 dark:text-neutral-400">{t('settings.data.githubRepoNameHint')}</p>
        <button
          type="button"
          disabled={busy || !githubAuthenticated}
          onClick={handleQuickStart}
          className="w-full px-4 py-3 bg-brutal-blue border-2 border-brutal-black font-black uppercase text-sm text-white shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 disabled:opacity-50"
        >
          {busy ? t('settings.data.working') : t('settings.data.githubQuickStartButton')}
        </button>
      </div>

      {configured && (
        <div className="flex flex-wrap gap-3 mt-4">
          <button type="button" disabled={busy} onClick={handlePush} className="px-4 py-2 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50">
            {t('settings.data.githubPush')}
          </button>
          <button type="button" disabled={busy} onClick={handlePull} className="px-4 py-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50">
            {t('settings.data.githubPull')}
          </button>
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
          <label className="block text-xs font-bold uppercase">
            {t('settings.data.githubRepoPlaceholder')}
            <input value={repoPath} onChange={(e) => setRepoPath(e.target.value)} className="mt-1 w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs dark:text-white" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs font-bold uppercase">
              {t('settings.data.githubBranch')}
              <input value={branch} onChange={(e) => setBranch(e.target.value)} className="mt-1 w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs dark:text-white" />
            </label>
            <label className="block text-xs font-bold uppercase">
              {t('settings.data.githubRemote')}
              <input value={remote} onChange={(e) => setRemote(e.target.value)} className="mt-1 w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs dark:text-white" />
            </label>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="flex items-center gap-2 border-2 border-brutal-black px-3 py-2 text-xs font-bold uppercase bg-neutral-50 dark:bg-zinc-900">
              <input type="checkbox" checked={autoSync} onChange={(e) => setAutoSync(e.target.checked)} />
              {t('settings.data.githubAutoSync')}
            </label>
            <label className="flex items-center gap-2 border-2 border-brutal-black px-3 py-2 text-xs font-bold uppercase bg-neutral-50 dark:bg-zinc-900">
              <input type="checkbox" checked={autoResolve} onChange={(e) => setAutoResolve(e.target.checked)} />
              {t('settings.data.githubAutoResolve')}
            </label>
            <label className="flex items-center gap-2 border-2 border-brutal-black px-3 py-2 text-xs font-bold uppercase bg-neutral-50 dark:bg-zinc-900">
              {t('settings.data.githubInterval')}
              <input type="number" min={1} value={intervalHours} onChange={(e) => setIntervalHours(Number(e.target.value) || 4)} className="w-16 bg-white dark:bg-zinc-800 border-2 border-brutal-black px-2 py-1" />
            </label>
          </div>
          <ShibbolethPanel profile={syncStatus?.profile} syncStatus={syncStatus} busy={busy} onBusyChange={onBusyChange} onNotify={onNotify} onChanged={refresh} />
          <div className="flex flex-wrap gap-3">
            <button type="button" disabled={busy || !repoPath.trim()} onClick={handleSaveProfile} className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50">{t('settings.data.githubSave')}</button>
            <button type="button" disabled={busy || !repoPath.trim()} onClick={handleValidate} className="px-4 py-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50">{t('settings.data.githubValidate')}</button>
            <button type="button" disabled={busy || !syncStatus?.profile} onClick={handleSaveAutomation} className="px-4 py-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50">{t('settings.data.githubSaveAuto')}</button>
          </div>
          {syncStatus?.profile?.last_revision !== undefined && (
            <p className="font-mono text-xs text-neutral-600 dark:text-neutral-400">
              {t('settings.data.githubLastRevision')}: {syncStatus.profile.last_revision || t('settings.data.githubNone')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
