import { useEffect, useState } from 'react';
import { Cog6ToothIcon } from '@heroicons/react/24/outline';
import { useChatCoreStore } from '../../hooks/useChatStore';
import { useHeartbeatPulse } from '../../hooks/useHeartbeatPulse';
import { useHeartbeatToggle } from '../../hooks/useHeartbeatToggle';
import { useProjects } from '../../hooks/useProjects';
import { useI18n } from '../../i18n';
import { fetchChatGitStatus, type GitRepositoryStatus } from '../../lib/api';
import { FOCAL_CHAT_ID } from '../../lib/focalAgent';
import { BrutalOnOff } from '../BrutalOnOff';
import { HeartbeatPulse } from '../HeartbeatPulse';
import { ProjectSettingsDialog, SYSTEM_PROJECT_SLUGS } from '../ProjectSettingsDialog';

const GIT_STATUS_POLL_MS = 10_000;

function folderName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

function useEnvironment() {
  const { config, backendConfig } = useChatCoreStore();
  const prefs = backendConfig?.userPreferences;
  return {
    model: config?.model || prefs?.model || backendConfig?.models?.[0] || null,
    sandbox: !!(config?.sandbox_enabled ?? prefs?.sandbox_enabled ?? backendConfig?.sandboxEnabled),
    permissionMode: config?.permission_mode ?? 'auto',
    // Volumes are "host:container"; the host side is what the user picked.
    volumes: (config?.sandbox_volumes ?? []).map((volume) =>
      volume.includes(':', 2) ? volume.substring(0, volume.lastIndexOf(':')) : volume
    ),
  };
}

function useChatGitRepositories(): GitRepositoryStatus[] {
  const { currentChatId, config } = useChatCoreStore();
  const project = useCurrentProject();
  const [repositories, setRepositories] = useState<GitRepositoryStatus[]>([]);
  const volumesKey = (config?.sandbox_volumes ?? []).join('|');
  const projectFoldersKey = [
    project?.workingDirectory ?? '',
    ...(project?.extraFolders ?? []),
  ].join('|');

  useEffect(() => {
    if (!currentChatId || currentChatId === FOCAL_CHAT_ID) {
      setRepositories([]);
      return;
    }

    let active = true;
    const refresh = async () => {
      try {
        const res = await fetchChatGitStatus(currentChatId);
        if (!active) return;
        setRepositories(res.repositories || []);
      } catch {
        if (!active) return;
        setRepositories([]);
      }
    };

    void refresh();
    const interval = window.setInterval(refresh, GIT_STATUS_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [currentChatId, volumesKey, projectFoldersKey]);

  return repositories;
}

/** One collapsed line: where and how this chat runs, plus active Git status. */
export function EnvironmentPreview(): JSX.Element {
  const { t } = useI18n();
  const env = useEnvironment();
  const repositories = useChatGitRepositories();
  const parts = [
    env.model?.split('/').pop(),
    t(env.sandbox ? 'sidebar.environment.sandbox' : 'sidebar.environment.host'),
    t(`chatWindow.permissionModeInputLabels.${env.permissionMode}`),
  ].filter(Boolean);

  const primaryRepo = repositories[0];
  const extraCount = repositories.length - 1;
  const totalAdditions = repositories.reduce((sum, r) => sum + r.additions, 0);
  const totalDeletions = repositories.reduce((sum, r) => sum + r.deletions, 0);
  const totalChanged = repositories.reduce((sum, r) => sum + r.total_changed, 0);

  return (
    <div className="mt-1 space-y-1 text-xs text-neutral-500 dark:text-neutral-400">
      <div className="truncate">{parts.join(' · ')}</div>
      {primaryRepo && (
        <div className="flex items-center gap-1.5 truncate font-mono text-[11px]">
          <span aria-hidden="true">⎇</span>
          {repositories.length > 1 && (
            <span className="truncate text-neutral-600 dark:text-neutral-300">
              {primaryRepo.name}:
            </span>
          )}
          <span className="truncate text-neutral-700 dark:text-neutral-200">
            {primaryRepo.branch}
          </span>
          {(totalAdditions > 0 || totalDeletions > 0) && (
            <span className="inline-flex shrink-0 items-center gap-1">
              {totalAdditions > 0 && (
                <span className="text-emerald-700 dark:text-emerald-400">+{totalAdditions}</span>
              )}
              {totalDeletions > 0 && (
                <span className="text-rose-700 dark:text-rose-400">-{totalDeletions}</span>
              )}
            </span>
          )}
          {totalChanged > 0 && totalAdditions === 0 && totalDeletions === 0 && (
            <span className="shrink-0 text-amber-700 dark:text-amber-300">●{totalChanged}</span>
          )}
          {extraCount > 0 && (
            <span className="shrink-0 rounded bg-neutral-200/80 px-1 text-[10px] text-neutral-600 dark:bg-zinc-700 dark:text-neutral-300">
              +{extraCount}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  children,
  title,
}: {
  label: string;
  children: React.ReactNode;
  title?: string;
}): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-xs">
      <span className="shrink-0 text-neutral-500 dark:text-neutral-400">{label}</span>
      <span
        className="min-w-0 truncate text-right text-neutral-700 dark:text-neutral-200"
        title={title}
      >
        {children}
      </span>
    </div>
  );
}

/** The current chat's project; the chat list may not hold chats opened from a project. */
function useCurrentProject() {
  const { currentChatProjectId } = useChatCoreStore();
  return useProjects().getProject(currentChatProjectId);
}

export function EnvironmentProjectName(): JSX.Element | null {
  const project = useCurrentProject();
  return project ? <>{project.name}</> : null;
}

export function EnvironmentSummary(): JSX.Element {
  const { t } = useI18n();
  const env = useEnvironment();
  const repositories = useChatGitRepositories();
  const { updateProjectSettings } = useProjects();
  const project = useCurrentProject();
  const heartbeat = useHeartbeatToggle();
  const pulse = useHeartbeatPulse();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const workingDirectory = project?.workingDirectory;
  const folders = [...new Set([...(project?.extraFolders ?? []), ...env.volumes])].filter(
    (folder) => folder !== workingDirectory
  );

  return (
    <div className="mb-1">
      {project && (
        <div className="flex items-center justify-between gap-3 py-1 text-xs">
          <span className="shrink-0 text-neutral-500 dark:text-neutral-400">
            {t('sidebar.environment.project')}
          </span>
          <span className="flex min-w-0 items-center gap-1 text-neutral-700 dark:text-neutral-200">
            <span className="truncate">{project.name}</span>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              title={t('projectSettings.title')}
              aria-label={t('projectSettings.title')}
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-neutral-400 hover:bg-neutral-200 hover:text-brutal-black dark:hover:bg-zinc-700 dark:hover:text-white"
            >
              <Cog6ToothIcon className="h-3.5 w-3.5" />
            </button>
          </span>
        </div>
      )}
      {workingDirectory && (
        <Row label={t('folderContext.context')} title={workingDirectory}>
          <span className="font-mono text-[11px]">{folderName(workingDirectory)}</span>
        </Row>
      )}
      {folders.length > 0 && (
        <Row label={t('sidebar.environment.mounted')} title={folders.join('\n')}>
          <span className="font-mono text-[11px]">{folders.map(folderName).join(', ')}</span>
        </Row>
      )}
      {repositories.length > 0 && (
        <div className="my-1.5 space-y-1.5 border-y border-neutral-200/80 py-1.5 dark:border-zinc-700/80">
          <div className="flex items-center justify-between text-[11px] text-neutral-500 dark:text-neutral-400">
            <span>
              {t(repositories.length === 1 ? 'status.gitHeaderOne' : 'status.gitHeaderMany', {
                count: String(repositories.length),
              })}
            </span>
            {repositories.some((r) => !r.clean) ? (
              <span className="font-mono text-[10px] text-amber-700 dark:text-amber-300">
                {t('status.gitDirtyCount', {
                  count: String(repositories.filter((r) => !r.clean).length),
                })}
              </span>
            ) : (
              <span className="font-mono text-[10px] text-emerald-700 dark:text-emerald-400">
                {t('status.gitAllClean')}
              </span>
            )}
          </div>
          {repositories.map((repo) => (
            <div
              key={repo.path}
              className="rounded border border-neutral-200 bg-neutral-50/70 p-2 text-xs dark:border-zinc-700/80 dark:bg-zinc-800/50"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5 font-medium text-neutral-800 dark:text-neutral-100">
                  <span className="truncate" title={repo.path}>
                    {repo.name}
                  </span>
                  {repo.primary && repositories.length > 1 && (
                    <span className="rounded border border-neutral-400 px-1 font-mono text-[9px] uppercase text-neutral-600 dark:border-zinc-600 dark:text-neutral-300">
                      {t('status.gitPrimaryCwd')}
                    </span>
                  )}
                </div>
                <span className="shrink-0 font-mono text-[11px] text-neutral-600 dark:text-neutral-300">
                  ⎇ {repo.branch}
                  {repo.ahead > 0 ? ` ↑${repo.ahead}` : ''}
                  {repo.behind > 0 ? ` ↓${repo.behind}` : ''}
                </span>
              </div>

              {repo.clean ? (
                <div className="mt-1 font-mono text-[10px] text-emerald-700 dark:text-emerald-400">
                  {t('status.gitWorkingTreeClean')}
                </div>
              ) : (
                <div className="mt-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] text-neutral-600 dark:text-neutral-300">
                    {(repo.additions > 0 || repo.deletions > 0) && (
                      <span>
                        <span className="text-emerald-700 dark:text-emerald-400">
                          +{repo.additions}
                        </span>{' '}
                        <span className="text-rose-700 dark:text-rose-400">-{repo.deletions}</span>
                      </span>
                    )}
                    {repo.staged > 0 && (
                      <span>{t('status.gitStagedCount', { count: String(repo.staged) })}</span>
                    )}
                    {repo.modified > 0 && (
                      <span>{t('status.gitModifiedCount', { count: String(repo.modified) })}</span>
                    )}
                    {repo.untracked > 0 && (
                      <span>
                        {t('status.gitUntrackedCount', { count: String(repo.untracked) })}
                      </span>
                    )}
                    {repo.conflicted > 0 && (
                      <span className="text-rose-700 dark:text-rose-400">
                        {t('status.gitConflictedCount', { count: String(repo.conflicted) })}
                      </span>
                    )}
                  </div>

                  {repo.files.length > 0 && (
                    <div className="max-h-28 space-y-0.5 overflow-y-auto border-t border-neutral-200/80 pt-1 font-mono text-[10px] dark:border-zinc-700/80">
                      {repo.files.map((file) => (
                        <div key={file.path} className="flex items-center gap-1.5 truncate">
                          <span className="w-3 shrink-0 text-center font-bold text-neutral-500 dark:text-neutral-400">
                            {file.status}
                          </span>
                          <span
                            className="truncate text-neutral-700 dark:text-neutral-300"
                            title={file.path}
                          >
                            {file.path}
                          </span>
                        </div>
                      ))}
                      {repo.total_changed > repo.files.length && (
                        <div className="text-[9px] text-neutral-400">
                          {t('status.gitMoreFiles', {
                            count: String(repo.total_changed - repo.files.length),
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <Row label={t('sidebar.environment.runsIn')}>
        {t(env.sandbox ? 'sidebar.environment.sandbox' : 'sidebar.environment.host')}
      </Row>
      {env.model && (
        <Row label={t('sidebar.environment.model')} title={env.model}>
          <span className="font-mono text-[11px]">{env.model.split('/').pop()}</span>
        </Row>
      )}
      <Row label={t('sidebar.environment.permissions')}>
        {t(`chatWindow.permissionModeInputLabels.${env.permissionMode}`)}
      </Row>
      <div className="flex items-center justify-between gap-3 py-1 text-xs">
        <span className="text-neutral-500 dark:text-neutral-400">
          {t('chatWindow.heartbeatLabel')}
        </span>
        <span className="flex items-center gap-2">
          <span
            title={pulse.text}
            className={`flex items-center gap-1 ${
              pulse.failure && pulse.enabled && !pulse.inFlightForChat
                ? 'text-red-600 dark:text-red-400'
                : 'text-neutral-500 dark:text-neutral-400'
            } ${pulse.enabled ? '' : 'opacity-40'}`}
          >
            <HeartbeatPulse pulse={pulse} />
            <span className="sr-only">{pulse.text}</span>
          </span>
          <BrutalOnOff
            size="sm"
            checked={heartbeat.enabled}
            onChange={() => void heartbeat.toggle()}
            disabled={heartbeat.toggling}
          />
        </span>
      </div>
      {settingsOpen && project && (
        <ProjectSettingsDialog
          project={project}
          canRename={!SYSTEM_PROJECT_SLUGS.has(project.slug)}
          onSave={(update) => updateProjectSettings(project.id, update)}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
