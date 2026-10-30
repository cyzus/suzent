import { useState } from 'react';
import { Cog6ToothIcon } from '@heroicons/react/24/outline';
import { useChatCoreStore } from '../../hooks/useChatStore';
import { useHeartbeatPulse } from '../../hooks/useHeartbeatPulse';
import { useHeartbeatToggle } from '../../hooks/useHeartbeatToggle';
import { useProjects } from '../../hooks/useProjects';
import { useI18n } from '../../i18n';
import { BrutalOnOff } from '../BrutalOnOff';
import { HeartbeatPulse } from '../HeartbeatPulse';
import { ProjectSettingsDialog, SYSTEM_PROJECT_SLUGS } from '../ProjectSettingsDialog';

function folderName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

function useEnvironment() {
  const { config, backendConfig } = useChatCoreStore();
  const prefs = backendConfig?.userPreferences;
  return {
    model: config?.model || prefs?.model || backendConfig?.models?.[0] || null,
    sandbox: !!(config?.sandbox_enabled ?? prefs?.sandbox_enabled ?? backendConfig?.sandboxEnabled),
    permissionMode: config?.permission_mode ?? 'default',
    // Volumes are "host:container"; the host side is what the user picked.
    volumes: (config?.sandbox_volumes ?? []).map((volume) =>
      volume.includes(':', 2) ? volume.substring(0, volume.lastIndexOf(':')) : volume
    ),
  };
}

/** One collapsed line: where and how this chat runs. */
export function EnvironmentPreview(): JSX.Element {
  const { t } = useI18n();
  const env = useEnvironment();
  const parts = [
    env.model?.split('/').pop(),
    t(env.sandbox ? 'sidebar.environment.sandbox' : 'sidebar.environment.host'),
    t(`chatWindow.permissionModeInputLabels.${env.permissionMode}`),
  ].filter(Boolean);
  return (
    <div className="mt-1 truncate text-xs text-neutral-500 dark:text-neutral-400">
      {parts.join(' · ')}
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
