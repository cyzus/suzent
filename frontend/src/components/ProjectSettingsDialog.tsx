import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Project } from '../types/api';
import { useI18n } from '../i18n';
import { isImeComposing } from '../lib/ime';
import { getApiBase } from '../lib/api';
import { FolderContextPicker } from './chat/FolderContextPicker';

export interface ProjectSettingsUpdate {
  name?: string;
  workingDirectory?: string | null;
}

interface ProjectSettingsDialogProps {
  project: Project;
  /** System projects (Home, Social) keep their name. */
  canRename: boolean;
  onSave: (update: ProjectSettingsUpdate) => Promise<{ success: boolean; error?: string }>;
  onClose: () => void;
  /** Extra data-* attributes stamped on the dialog root (e.g. for outside-click whitelisting). */
  rootDataAttrs?: Record<string, string>;
}

const INPUT_CLASS =
  'w-full min-w-0 px-2 py-1.5 text-xs bg-white dark:bg-zinc-800 dark:text-white border-2 border-brutal-black dark:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-brutal-blue';
const PICKER_BUTTON_CLASS =
  'flex items-center gap-1.5 w-full min-w-0 px-2 py-1.5 text-xs font-mono bg-white dark:bg-zinc-800 text-brutal-black dark:text-white border-2 border-brutal-black dark:border-zinc-500 hover:bg-neutral-100 dark:hover:bg-zinc-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue';

/**
 * Per-project settings. The working directory set here is the default cwd for
 * every chat in the project; a chat that has its own working directory keeps it.
 */
export const ProjectSettingsDialog: React.FC<ProjectSettingsDialogProps> = ({
  project,
  canRename,
  onSave,
  onClose,
  rootDataAttrs,
}) => {
  const { t } = useI18n();
  const [name, setName] = useState(project.name);
  const [workingDirectory, setWorkingDirectory] = useState(project.workingDirectory ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectFolders, setProjectFolders] = useState<string[]>([]);
  const nameRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${getApiBase()}/projects/${project.id}/folders`)
      .then((res) => (res.ok ? res.json() : { folders: [] }))
      .then((data: { folders?: string[] }) => {
        if (!cancelled) setProjectFolders(data.folders ?? []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isImeComposing(e)) return;
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const focus = setTimeout(() => nameRef.current?.focus(), 0);
    return () => {
      document.removeEventListener('keydown', onKey);
      clearTimeout(focus);
    };
  }, [onClose, canRename]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const update: ProjectSettingsUpdate = {};
    const trimmedName = name.trim();
    if (canRename && trimmedName && trimmedName !== project.name) update.name = trimmedName;
    const trimmedDirectory = workingDirectory.trim();
    if (trimmedDirectory !== (project.workingDirectory ?? '')) {
      update.workingDirectory = trimmedDirectory || null;
    }
    if (Object.keys(update).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    const result = await onSave(update);
    setSaving(false);
    if (result.success) onClose();
    else setError(result.error || t('projectSettings.saveFailed'));
  };

  const dialog = (
    <div
      className="fixed inset-0 z-[9998] flex items-center justify-center p-4 animate-brutal-drop"
      style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      {...(rootDataAttrs || {})}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-settings-title"
        onSubmit={save}
        className="relative w-full max-w-md bg-white dark:bg-zinc-900 border-2 border-brutal-black dark:border-zinc-500 shadow-[5px_5px_0_0_#000] dark:shadow-[5px_5px_0_0_rgba(255,255,255,0.15)]"
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b-2 border-brutal-black dark:border-zinc-500">
          <h2
            id="project-settings-title"
            className="flex-1 min-w-0 truncate text-sm font-extrabold uppercase tracking-wider text-brutal-black dark:text-white"
          >
            {t('projectSettings.title', { name: project.name })}
          </h2>
          <button
            type="button"
            aria-label={t('common.cancel')}
            onClick={onClose}
            className="ml-auto p-1 text-brutal-black dark:text-white hover:bg-brutal-black/10 dark:hover:bg-white/10 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-4 px-4 py-4 text-sm text-neutral-700 dark:text-neutral-300">
          {canRename && (
            <label className="block space-y-1">
              <span className="block text-[10px] font-extrabold uppercase tracking-wide text-brutal-black dark:text-white">
                {t('projectSettings.name')}
              </span>
              <input
                ref={nameRef}
                value={name}
                onChange={(event) => setName(event.target.value)}
                className={`${INPUT_CLASS} font-bold`}
              />
            </label>
          )}

          <div className="space-y-1">
            <span className="block text-[10px] font-extrabold uppercase tracking-wide text-brutal-black dark:text-white">
              {t('projectSettings.workingDirectory')}
            </span>
            <FolderContextPicker
              multiple={false}
              activeFolders={workingDirectory ? [workingDirectory] : []}
              projectFolders={projectFolders}
              onMount={(paths) => setWorkingDirectory(paths[0] ?? '')}
              onRemoveVolume={() => setWorkingDirectory('')}
              activeTitle={t('projectSettings.workingDirectory')}
              emptyActiveText={t('projectSettings.workingDirectoryPlaceholder')}
              buttonLabel={workingDirectory || t('projectSettings.workingDirectoryPlaceholder')}
              buttonClassName={PICKER_BUTTON_CLASS}
              dropUp={false}
            />
            <p className="text-[11px] leading-snug text-neutral-500 dark:text-neutral-400">
              {t('projectSettings.workingDirectoryHelp')}
            </p>
          </div>

          {error && (
            <p role="alert" className="text-xs font-bold text-brutal-red dark:text-red-400">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-stretch border-t-2 border-brutal-black dark:border-zinc-500">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-3 text-xs font-bold uppercase tracking-wide transition-colors bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
          >
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex-1 py-3 text-xs font-bold uppercase tracking-wide transition-colors border-l-2 border-brutal-black dark:border-zinc-500 bg-brutal-black text-white hover:bg-neutral-800 dark:bg-brutal-yellow dark:text-brutal-black dark:hover:bg-yellow-300 disabled:opacity-60"
          >
            {t('projectSettings.save')}
          </button>
        </div>
      </form>
    </div>
  );

  return createPortal(dialog, document.body);
};
