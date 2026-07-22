import React, { useCallback, useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  fetchGitHubAuthStatus,
  fetchSyncAheadBehind,
  fetchSyncQuickstartInfo,
  fetchSyncStatus,
  githubSyncDiscardOutgoing,
  githubSyncPlan,
  githubSyncPull,
  githubSyncPush,
  logoutGitHub,
  pollGitHubAuth,
  runSync,
  runSyncQuickstart,
  saveSyncAutoConfig,
  saveSyncProfile,
  startGitHubAuth,
  syncReviewPlanFromError,
  SyncFileChange,
  SyncDirection,
  SyncOperation,
  SyncPlan,
  SyncProfile,
  SyncStatus,
} from '../../lib/dataApi';
import { SettingsCard, SectionCardHeader, Badge, SettingsListAction } from './SettingsCard';
import { BrutalButton } from '../BrutalButton';

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
  muted,
}: {
  children: React.ReactNode;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  title?: string;
  primary?: boolean;
  muted?: boolean;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={() => { void onClick(); }}
      disabled={disabled}
      title={title}
      className={`flex items-center gap-1.5 px-3 py-2 border-l-2 border-brutal-black font-bold uppercase text-xs disabled:opacity-40 hover:brightness-95 dark:hover:brightness-125 transition-all ${
        primary
          ? 'bg-brutal-blue text-white'
          : muted
            ? 'bg-neutral-50 dark:bg-zinc-900 text-neutral-400 dark:text-neutral-600'
            : 'bg-neutral-50 dark:bg-zinc-900 text-brutal-black dark:text-white'
      }`}
    >
      {children}
    </button>
  );
}

const SYNC_METADATA_PREFIX = '_sync/';

function SyncedFilesPanel({ hashes }: { hashes?: Record<string, string> }): React.ReactElement | null {
  const [open, setOpen] = useState(false);
  // Group portable payload files by top-level directory and hide sync metadata.
  const groups: Record<string, string[]> = {};
  for (const rel of Object.keys(hashes ?? {})) {
    if (rel.startsWith(SYNC_METADATA_PREFIX) || rel === 'manifest.json') continue;
    const top = rel.split('/')[0] || 'other';
    (groups[top] ??= []).push(rel);
  }
  const groupNames = Object.keys(groups).sort();
  const total = groupNames.reduce((n, g) => n + groups[g].length, 0);
  if (total === 0) return null;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between border-2 border-brutal-black px-3 py-2 text-xs font-bold uppercase bg-neutral-50 dark:bg-zinc-900"
      >
        <span>Synced files ({total})</span>
        <span>{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="mt-2 border-2 border-brutal-black bg-white dark:bg-zinc-900 divide-y divide-brutal-black/10 max-h-56 overflow-y-auto">
          {groupNames.map((g) => (
            <div key={g} className="px-3 py-2">
              <p className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">
                {g} <span className="text-neutral-300 dark:text-neutral-600">({groups[g].length})</span>
              </p>
              <ul className="space-y-0.5">
                {groups[g].sort().map((rel) => (
                  <li key={rel} className="font-mono text-[11px] truncate dark:text-neutral-300" title={rel}>
                    {rel.slice(g.length + 1) || rel}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function syncChangeStatus(changeType: SyncFileChange['change_type']): string {
  if (changeType === 'added') return 'A';
  if (changeType === 'deleted') return 'D';
  return 'M';
}

function syncChangeTone(change: SyncFileChange): string {
  if (change.risk === 'high') return 'text-red-600 dark:text-red-300';
  if (change.change_type === 'added') return 'text-green-600 dark:text-green-300';
  if (change.change_type === 'deleted') return 'text-red-600 dark:text-red-300';
  return 'text-amber-600 dark:text-amber-300';
}

function syncDisplayName(change: SyncFileChange): string {
  return change.path.split('/').pop() || change.path;
}

function syncDisplayDir(change: SyncFileChange): string {
  const parts = change.path.split('/');
  parts.pop();
  return parts.join('/') || change.category;
}

function syncGroupLabel(category: SyncFileChange['category']): string {
  return category;
}

function shouldShowSyncChange(change: SyncFileChange): boolean {
  if (change.category === 'sync') return change.risk !== 'low';
  if (change.path === 'memory/.index_state.json') return false;
  return true;
}

function syncDirectionOf(change: SyncFileChange): SyncDirection {
  return change.direction ?? 'outgoing';
}

function syncPlanKey(plan: SyncPlan): string {
  const files = plan.files
    .filter(shouldShowSyncChange)
    .map((file) => `${file.change_type}:${file.risk}:${file.category}:${file.path}`)
    .sort()
    .join('|');
  return `${plan.operation}:${files}`;
}

type DiffRowKind = 'add' | 'delete' | 'hunk' | 'context';

function diffRows(diffPreview: string): { kind: DiffRowKind; text: string }[] {
  return diffPreview
    .split('\n')
    .filter((line) => (
      !line.startsWith('diff --git ')
      && !line.startsWith('index ')
      && !line.startsWith('deleted file mode ')
      && !line.startsWith('new file mode ')
      && !line.startsWith('--- ')
      && !line.startsWith('+++ ')
    ))
    .map((line) => {
      if (line.startsWith('@@')) return { kind: 'hunk', text: line };
      if (line.startsWith('+')) return { kind: 'add', text: line.slice(1) };
      if (line.startsWith('-')) return { kind: 'delete', text: line.slice(1) };
      return { kind: 'context', text: line.startsWith(' ') ? line.slice(1) : line };
    });
}

function DiffPreview({ value }: { value: string }): React.ReactElement {
  const { t } = useI18n();
  const rows = diffRows(value);
  return (
    <div className="mx-3 mb-2 max-h-56 overflow-auto border border-neutral-300 bg-[#ffffff] font-mono text-[10px] leading-relaxed dark:border-zinc-700 dark:bg-[#1e1e1e]">
      <div className="border-b border-neutral-200 bg-[#f3f3f3] px-2 py-1 text-[10px] font-bold uppercase text-neutral-500 dark:border-zinc-700 dark:bg-[#252526] dark:text-neutral-400">
        {t('settings.data.githubReviewDiff')}
      </div>
      {rows.length === 0 ? (
        <div className="px-2 py-1 text-neutral-400 dark:text-neutral-500">
          {t('settings.data.githubReviewNoDiff')}
        </div>
      ) : (
        rows.map((row, index) => {
          const tone = row.kind === 'add'
            ? 'bg-green-50 text-green-900 dark:bg-green-950/30 dark:text-green-200'
            : row.kind === 'delete'
              ? 'bg-red-50 text-red-900 dark:bg-red-950/30 dark:text-red-200'
              : row.kind === 'hunk'
                ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300'
                : 'text-neutral-700 dark:text-neutral-300';
          const marker = row.kind === 'add' ? '+' : row.kind === 'delete' ? '-' : row.kind === 'hunk' ? '@' : ' ';
          return (
            <div key={`${index}:${row.text}`} className={`grid grid-cols-[24px_1fr] ${tone}`}>
              <span className="select-none border-r border-black/10 px-1 text-right text-neutral-400 dark:border-white/10 dark:text-neutral-500">
                {marker}
              </span>
              <span className="whitespace-pre-wrap px-2">{row.text || ' '}</span>
            </div>
          );
        })
      )}
    </div>
  );
}

function SyncReviewPanel({
  plan,
  busy,
  onCancel,
  onConfirm,
  onDiscardOutgoing,
  onDiscardFile,
  onPullCloud,
}: {
  plan: SyncPlan;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onDiscardOutgoing: () => void;
  onDiscardFile: (file: SyncFileChange) => void;
  onPullCloud: () => void;
}): React.ReactElement {
  const { t } = useI18n();
  const reviewFiles = plan.files.filter(shouldShowSyncChange);
  const visibleFiles = reviewFiles.slice(0, 80);
  const hiddenCount = Math.max(0, reviewFiles.length - visibleFiles.length);
  const hiddenMetadataCount = plan.files.length - reviewFiles.length;
  const summary = reviewFiles.reduce(
    (acc, file) => {
      acc[file.change_type] += 1;
      if (file.risk === 'high') acc.high_risk += 1;
      return acc;
    },
    { added: 0, modified: 0, deleted: 0, high_risk: 0 },
  );
  const operationLabel = plan.operation === 'auto'
    ? t('settings.data.githubReviewSync')
    : plan.operation === 'pull'
      ? t('settings.data.githubPull')
      : t('settings.data.githubPush');
  const directionGroups = visibleFiles.reduce<Record<SyncDirection, Record<string, SyncFileChange[]>>>((acc, file) => {
    const direction = syncDirectionOf(file);
    const category = syncGroupLabel(file.category);
    (acc[direction][category] ??= []).push(file);
    return acc;
  }, { outgoing: {}, incoming: {} });
  const sortedCategoryNames = (groups: Record<string, SyncFileChange[]>): string[] => Object.keys(groups).sort((a, b) => {
    const order = ['memory', 'config', 'skills', 'sync', 'other'];
    return (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) - (order.indexOf(b) === -1 ? 99 : order.indexOf(b));
  });
  const directionOrder: SyncDirection[] = ['outgoing', 'incoming'];
  const outgoingCount = directionOrder.includes('outgoing')
    ? Object.values(directionGroups.outgoing).reduce((total, files) => total + files.length, 0)
    : 0;
  const incomingCount = directionOrder.includes('incoming')
    ? Object.values(directionGroups.incoming).reduce((total, files) => total + files.length, 0)
    : 0;

  return (
    <div className="mt-3 border-2 border-brutal-black bg-[#f3f3f3] dark:bg-[#181818]">
      <div className="flex items-center justify-between border-b-2 border-brutal-black bg-[#eeeeee] dark:bg-[#252526] px-3 py-2">
        <div className="min-w-0">
          <p className="text-[11px] font-black uppercase text-neutral-700 dark:text-neutral-200">
            {t('settings.data.githubReviewTitle')}
          </p>
          <p className="mt-0.5 text-[10px] font-mono text-neutral-500 dark:text-neutral-400 truncate">
            {t('settings.data.githubReviewSubtitle', { operation: operationLabel })}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="font-mono text-[10px] font-bold text-green-700 dark:text-green-300" title={t('settings.data.githubReviewAdded')}>
            +{summary.added ?? 0}
          </span>
          <span className="font-mono text-[10px] font-bold text-amber-700 dark:text-amber-300" title={t('settings.data.githubReviewModified')}>
            ~{summary.modified ?? 0}
          </span>
          <span className="font-mono text-[10px] font-bold text-red-700 dark:text-red-300" title={t('settings.data.githubReviewDeleted')}>
            -{summary.deleted ?? 0}
          </span>
        </div>
      </div>

      {plan.warnings.length > 0 && (
        <div className="border-b border-brutal-black/20 bg-red-50 dark:bg-red-950/30 px-3 py-2">
          {plan.warnings.map((warning) => (
            <p key={warning} className="text-[11px] font-bold text-red-700 dark:text-red-300">
              {warning}
            </p>
          ))}
        </div>
      )}

      <div className="max-h-72 overflow-y-auto bg-[#f8f8f8] dark:bg-[#1e1e1e]">
        {directionOrder.map((direction) => {
          const categoryGroups = directionGroups[direction];
          const categoryNames = sortedCategoryNames(categoryGroups);
          const count = categoryNames.reduce((total, category) => total + (categoryGroups[category]?.length ?? 0), 0);
          if (count === 0) return null;
          return (
            <div key={direction} className="border-b-2 border-brutal-black/20 last:border-b-0">
              <div className="flex items-center justify-between bg-[#dddddd] dark:bg-[#303030] px-3 py-1.5">
                <span className="text-[10px] font-black uppercase text-neutral-700 dark:text-neutral-200">
                  {direction === 'outgoing'
                    ? t('settings.data.githubReviewOutgoing')
                    : t('settings.data.githubReviewIncoming')}
                </span>
                <span className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400">{count}</span>
              </div>
              {categoryNames.map((group) => {
                const files = categoryGroups[group] ?? [];
                return (
                  <div key={`${direction}:${group}`} className="border-t border-brutal-black/10">
                    <div className="flex items-center justify-between bg-[#eeeeee] dark:bg-[#252526] px-3 py-1.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-[10px] text-neutral-500 dark:text-neutral-400">v</span>
                        <span className="text-[10px] font-black uppercase text-neutral-600 dark:text-neutral-300 truncate">
                          {t(`settings.data.githubReviewCategory${group.charAt(0).toUpperCase()}${group.slice(1)}`)}
                        </span>
                      </div>
                      <span className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                        {files.length}
                      </span>
                    </div>
                    <div>
                      {files.map((file) => (
                        <div key={`${syncDirectionOf(file)}:${file.change_type}:${file.path}`} className="border-t border-brutal-black/5 first:border-t-0">
                          <div
                            className="grid grid-cols-[18px_1fr_auto_28px] items-center gap-2 px-3 py-1.5 hover:bg-[#e8e8e8] dark:hover:bg-[#2a2d2e]"
                            title={file.path}
                          >
                            <span className={`font-mono text-[11px] font-black ${syncChangeTone(file)}`}>
                              {syncChangeStatus(file.change_type)}
                            </span>
                            <span className="min-w-0">
                              <span className="block truncate font-mono text-[12px] text-neutral-800 dark:text-neutral-100">
                                {syncDisplayName(file)}
                              </span>
                              <span className="block truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-500">
                                {syncDisplayDir(file)}
                              </span>
                            </span>
                            <span>
                              {syncDirectionOf(file) === 'outgoing' && (
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => onDiscardFile(file)}
                                  title={t('settings.data.githubReviewDiscardFileTitle')}
                                  className="border border-brutal-black/40 bg-white px-2 py-1 text-[9px] font-black uppercase text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:bg-zinc-900 dark:text-neutral-200 dark:hover:bg-zinc-800"
                                >
                                  {t('settings.data.githubReviewDiscardFile')}
                                </button>
                              )}
                            </span>
                            <span className={`text-right font-mono text-[10px] font-bold uppercase ${syncChangeTone(file)}`}>
                              {file.risk === 'high' ? '!' : file.risk === 'medium' ? '*' : ''}
                            </span>
                          </div>
                          {file.diff_preview && (
                            <DiffPreview value={file.diff_preview} />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
        {hiddenCount > 0 && (
          <div className="px-3 py-2 font-mono text-[11px] text-neutral-500 dark:text-neutral-400">
            {t('settings.data.githubReviewFilesHidden', { count: hiddenCount })}
          </div>
        )}
        {hiddenMetadataCount > 0 && (
          <div className="px-3 py-2 font-mono text-[10px] text-neutral-400 dark:text-neutral-500">
            {t('settings.data.githubReviewMetadataHidden', { count: hiddenMetadataCount })}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t-2 border-brutal-black bg-[#eeeeee] dark:bg-[#252526] px-3 py-2">
        <span className={`font-mono text-[10px] font-bold uppercase ${
          (summary.high_risk ?? 0) > 0
            ? 'text-red-700 dark:text-red-300'
            : 'text-neutral-500 dark:text-neutral-400'
        }`}>
          {t('settings.data.githubReviewHighRisk', { count: summary.high_risk ?? 0 })}
        </span>
        <div className="flex gap-2">
          {outgoingCount > 0 && (
            <button
              type="button"
              onClick={onDiscardOutgoing}
              disabled={busy}
              title={t('settings.data.githubReviewDiscardTitle')}
              className="px-3 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-xs font-bold uppercase disabled:opacity-50"
            >
              {t('settings.data.githubReviewDiscard')}
            </button>
          )}
          {incomingCount > 0 && (
            <button
              type="button"
              onClick={onPullCloud}
              disabled={busy}
              title={t('settings.data.githubReviewPullTitle')}
              className="px-3 py-2 border-2 border-brutal-black bg-blue-600 text-white text-xs font-black uppercase disabled:opacity-50"
            >
              {t('settings.data.githubReviewPull')}
            </button>
          )}
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-xs font-bold uppercase disabled:opacity-50"
          >
            {t('common.cancel')}
          </button>
          {!(outgoingCount > 0 && incomingCount > 0) && (
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy}
              className="px-3 py-2 border-2 border-brutal-black bg-red-600 text-white text-xs font-black uppercase disabled:opacity-50"
            >
              {t('settings.data.githubReviewConfirm', { operation: operationLabel })}
            </button>
          )}
        </div>
      </div>
    </div>
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
  const [githubAuthLoading, setGithubAuthLoading] = useState(true);
  const [githubAuthenticated, setGithubAuthenticated] = useState(false);
  const [githubUsername, setGithubUsername] = useState<string | null>(null);
  const [githubTokenExpired, setGithubTokenExpired] = useState(false);
  const [linkedRepo, setLinkedRepo] = useState<string | null>(null);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [ahead, setAhead] = useState<number | null>(null);
  const [behind, setBehind] = useState<number | null>(null);
  const [reviewPlan, setReviewPlan] = useState<SyncPlan | null>(null);
  const [reviewOperation, setReviewOperation] = useState<SyncOperation | null>(null);
  const [dismissedPlanKey, setDismissedPlanKey] = useState<string | null>(null);

  const [devicePhase, setDevicePhase] = useState<DeviceFlowPhase>('idle');
  const [deviceCode, setDeviceCode] = useState('');
  const [deviceUrl, setDeviceUrl] = useState('');
  const [deviceSessionId, setDeviceSessionId] = useState('');
  const [deviceInterval, setDeviceInterval] = useState(5);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncPlanWatcherRunning = useRef(false);

  useEffect(() => {
    let cancelled = false;
    refresh().catch(() => {
      if (!cancelled) setSyncStatus(null);
    });
    fetchSyncQuickstartInfo()
      .then((info) => {
        if (cancelled) return;
        setRepoPath((current) => current || info.default_repo_path);
        if (!repoName) setRepoName(info.default_repo_name || 'suzent-brain');
      })
      .catch(() => {});
    fetchGitHubAuthStatus()
      .then((authStatus) => {
        if (cancelled) return;
        setGithubAuthenticated(authStatus.authenticated);
        setGithubUsername(authStatus.username ?? null);
        setGithubTokenExpired(authStatus.token_expired ?? false);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setGithubAuthLoading(false);
      });
    return () => {
      cancelled = true;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  useEffect(() => {
    const profileId = syncStatus?.configured ? syncStatus.profile?.id : null;
    if (!profileId) {
      setReviewPlan(null);
      setReviewOperation(null);
      setDismissedPlanKey(null);
      return;
    }

    let cancelled = false;
    const refreshWatchedPlan = async (): Promise<void> => {
      if (busy || syncPlanWatcherRunning.current) return;
      syncPlanWatcherRunning.current = true;
      try {
        const plan = await githubSyncPlan('auto', profileId);
        if (cancelled) return;
        if (plan.files.filter(shouldShowSyncChange).length === 0) {
          setReviewPlan((current) => (current?.operation === 'auto' ? null : current));
          setReviewOperation((current) => (current === 'auto' ? null : current));
          setDismissedPlanKey(null);
          return;
        }

        const nextKey = syncPlanKey(plan);
        if (nextKey !== dismissedPlanKey) {
          setReviewPlan(plan);
          setReviewOperation('auto');
        }
      } catch {
        // A watcher should stay quiet; manual buttons still surface explicit errors.
      } finally {
        syncPlanWatcherRunning.current = false;
      }
    };

    void refreshWatchedPlan();
    const interval = window.setInterval(() => { void refreshWatchedPlan(); }, 8000);
    const handleFocus = (): void => { void refreshWatchedPlan(); };
    window.addEventListener('focus', handleFocus);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener('focus', handleFocus);
    };
  }, [syncStatus?.configured, syncStatus?.profile?.id, busy, dismissedPlanKey]);

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

  function openReview(plan: SyncPlan, operation: SyncOperation): void {
    setDismissedPlanKey(null);
    setReviewPlan(plan);
    setReviewOperation(operation);
    onNotify('Review sync changes before continuing.', true);
  }

  function makeSyncHandler(
    operation: SyncOperation,
    apiFn: (profileId: string, confirmDestructive?: boolean) => Promise<unknown>,
    successKey: string,
    notifyComplete = false,
  ) {
    return async function (confirmDestructive = false): Promise<void> {
      onBusyChange(true);
      try {
        const profile = syncStatus?.profile;
        if (!profile) throw new Error(t('settings.data.githubNotConfigured'));

        if (!confirmDestructive) {
          const plan = await githubSyncPlan(operation, profile.id);
          if (plan.requires_confirmation) {
            openReview(plan, operation);
            return;
          }
        }

        const result = (await apiFn(profile.id, confirmDestructive)) as
          | { blocked_review_required?: boolean; plan?: SyncPlan }
          | undefined;
        if (result?.blocked_review_required && result.plan) {
          openReview(result.plan, operation);
          return;
        }
        setReviewPlan(null);
        setReviewOperation(null);
        setDismissedPlanKey(null);
        await refresh();
        onNotify(t(successKey), false);
        if (notifyComplete) onSyncComplete?.();
      } catch (error) {
        const plan = syncReviewPlanFromError(error);
        if (plan) {
          openReview(plan, operation);
          return;
        }
        onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
      } finally {
        onBusyChange(false);
      }
    };
  }

  const handleSync = makeSyncHandler('auto', runSync, 'settings.data.githubPushed', true);
  const handlePull = makeSyncHandler(
    'pull',
    (profileId, confirmDestructive) => githubSyncPull(profileId, confirmDestructive),
    'settings.data.githubPulled',
    true,
  );
  const handlePush = makeSyncHandler(
    'push',
    (profileId, confirmDestructive) => githubSyncPush(profileId, confirmDestructive),
    'settings.data.githubPushed',
  );

  function handleReviewConfirm(): void {
    if (reviewOperation === 'auto') void handleSync(true);
    if (reviewOperation === 'pull') void handlePull(true);
    if (reviewOperation === 'push') void handlePush(true);
  }

  async function handleDiscardOutgoing(): Promise<void> {
    onBusyChange(true);
    try {
      const profile = syncStatus?.profile;
      if (!profile) throw new Error(t('settings.data.githubNotConfigured'));
      const result = await githubSyncDiscardOutgoing(profile.id) as { discarded?: string[] };
      setReviewPlan(null);
      setReviewOperation(null);
      setDismissedPlanKey(null);
      await refresh();
      const count = result.discarded?.length ?? 0;
      onNotify(
        count > 0
          ? t('settings.data.githubDiscardedOutgoing', { count })
          : t('settings.data.githubNoOutgoing'),
        false,
      );
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleDiscardFile(file: SyncFileChange): Promise<void> {
    onBusyChange(true);
    try {
      const profile = syncStatus?.profile;
      if (!profile) throw new Error(t('settings.data.githubNotConfigured'));
      await githubSyncDiscardOutgoing(profile.id, [file.path]);
      const plan = await githubSyncPlan(reviewOperation ?? 'auto', profile.id);
      if (plan.files.some(shouldShowSyncChange)) {
        setReviewPlan(plan);
      } else {
        setReviewPlan(null);
        setReviewOperation(null);
        setDismissedPlanKey(null);
      }
      await refresh();
      onNotify(t('settings.data.githubDiscardedFile', { path: file.path }), false);
    } catch (error) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handlePullCloud(): Promise<void> {
    onBusyChange(true);
    try {
      const profile = syncStatus?.profile;
      if (!profile) throw new Error(t('settings.data.githubNotConfigured'));
      await githubSyncPull(profile.id, true, true);
      setReviewPlan(null);
      setReviewOperation(null);
      setDismissedPlanKey(null);
      await refresh();
      onNotify(t('settings.data.githubCloudApplied'), false);
      onSyncComplete?.();
    } catch (error) {
      const plan = syncReviewPlanFromError(error);
      if (plan) {
        openReview(plan, 'pull');
        return;
      }
      onNotify(t('settings.data.githubFailed', { error: errMsg(error) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  const configured = Boolean(syncStatus?.configured && syncStatus.profile);

  return (
    <SettingsCard>
      <SectionCardHeader
        iconTone="black"
        icon={
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.48 2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49 0-.24-.01-.87-.01-1.71-2.78.62-3.37-1.22-3.37-1.22-.46-1.18-1.11-1.49-1.11-1.49-.91-.63.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.37-2.22-.26-4.56-1.14-4.56-5.05 0-1.12.39-2.03 1.03-2.74-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05a9.36 9.36 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.71 1.03 1.62 1.03 2.74 0 3.92-2.34 4.79-4.57 5.04.36.32.68.94.68 1.9 0 1.37-.01 2.48-.01 2.82 0 .27.18.6.69.49A10.02 10.02 0 0 0 22 12.25C22 6.58 17.52 2 12 2Z" />
          </svg>
        }
        title={t('settings.data.githubTitle')}
        description={
          <>
            {t('settings.data.githubDesc')}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {configured && <Badge tone="green">{t('settings.data.githubConnected')}</Badge>}
              {githubAuthenticated && (
                <>
                  <Badge tone="blue">
                    {githubUsername
                      ? t('settings.data.githubSignInDone', { username: githubUsername })
                      : t('settings.data.githubSignedIn')}
                  </Badge>
                  <SettingsListAction tone="red" onClick={handleSignOut}>
                    {t('settings.data.githubSignOut')}
                  </SettingsListAction>
                </>
              )}
            </div>
          </>
        }
      />

      {/* GitHub sign-in / device flow */}
      {!githubAuthLoading && githubTokenExpired && devicePhase === 'idle' && (
        <div className="mb-3 border-2 border-brutal-black bg-red-50 dark:bg-red-900/20 p-3 flex items-start gap-2">
          <span className="text-red-600 dark:text-red-400 text-xs font-bold uppercase shrink-0">⚠</span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-red-700 dark:text-red-400">GitHub token expired</p>
            <p className="text-[10px] text-red-600 dark:text-red-400 mt-0.5">Sign in again to re-authenticate.</p>
          </div>
        </div>
      )}
      {githubAuthLoading && devicePhase === 'idle' && (
        <div className="mb-4 flex items-center justify-center gap-2 border-2 border-brutal-black/20 bg-neutral-100 px-4 py-3 text-neutral-500 dark:bg-zinc-900 dark:text-neutral-400">
          <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path strokeLinecap="round" d="M8 2a6 6 0 1 1-4.243 1.757" />
          </svg>
          <span className="text-xs font-bold uppercase">
            {t('settings.data.githubCheckingAuth')}
          </span>
        </div>
      )}
      {!githubAuthLoading && !githubAuthenticated && devicePhase === 'idle' && (
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
            className="w-full px-4 py-2 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700 hover:brightness-110 text-left flex items-center justify-between brutal-btn"
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
            className="inline-block px-4 py-2 bg-brutal-black border-2 border-brutal-black font-bold uppercase text-xs text-white hover:brightness-110 brutal-btn"
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
            {/* Pull button — behind = commits on the remote not yet local */}
            <ActionBtn
              onClick={handlePull}
              disabled={busy}
              muted={behind === 0}
              title={behind && behind > 0 ? `Pull ${behind} update${behind !== 1 ? 's' : ''} from other devices` : 'Nothing to pull — up to date with the remote'}
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 2v9M5 8l3 3 3-3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2 13h12" />
              </svg>
              <span className="text-xs font-bold uppercase">
                {behind !== null && behind > 0 ? `Pull (${behind})` : 'Pull'}
              </span>
            </ActionBtn>
            {/* Push button — ahead = local commits not yet on the remote */}
            <ActionBtn
              onClick={handlePush}
              disabled={busy}
              muted={ahead === 0}
              title={ahead && ahead > 0 ? `Push ${ahead} local change${ahead !== 1 ? 's' : ''} to other devices` : 'Nothing to push — the remote has all your changes'}
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 14V5M5 8L8 5l3 3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2 3h12" />
              </svg>
              <span className="text-xs font-bold uppercase">
                {ahead !== null && ahead > 0 ? `Push (${ahead})` : 'Push'}
              </span>
            </ActionBtn>
            {/* Sync button — combined pull+push activity */}
            {(() => {
              const pending = (behind ?? 0) + (ahead ?? 0);
              return (
                <ActionBtn
                  onClick={handleSync}
                  disabled={busy}
                  muted={pending === 0}
                  title={pending > 0 ? `Sync: pull ${behind ?? 0} and push ${ahead ?? 0}` : 'Sync — already up to date'}
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2 6a6 6 0 0 1 10-2.5L14 5" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14 2v3h-3" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14 10a6 6 0 0 1-10 2.5L2 11" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2 14v-3h3" />
                  </svg>
                  <span className="text-xs font-bold uppercase">
                    {pending > 0 ? `Sync (${pending})` : 'Sync'}
                  </span>
                </ActionBtn>
              );
            })()}
          </>
        ) : (
          <ActionBtn onClick={handleQuickStart} disabled={busy || githubAuthLoading || !githubAuthenticated} title={t('settings.data.githubQuickStartButton')} primary>
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

      {configured && reviewPlan && (
        <SyncReviewPanel
          plan={reviewPlan}
          busy={busy}
          onCancel={() => {
            setDismissedPlanKey(syncPlanKey(reviewPlan));
            setReviewPlan(null);
            setReviewOperation(null);
          }}
          onConfirm={handleReviewConfirm}
          onDiscardOutgoing={() => { void handleDiscardOutgoing(); }}
          onDiscardFile={(file) => { void handleDiscardFile(file); }}
          onPullCloud={() => { void handlePullCloud(); }}
        />
      )}

      {configured && (
        <p className="mt-3 text-[10px] text-neutral-500 dark:text-neutral-400">
          {t('settings.data.githubFileOnlyScope')}
        </p>
      )}

      {configured && <SyncedFilesPanel hashes={syncStatus?.payload_hashes} />}

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
