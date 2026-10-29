import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Project } from '../types/api';
import { useI18n } from '../i18n';
import { isImeComposing } from '../lib/ime';
import { pickHostDirectory } from '../lib/hostPathPicker';

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
const SMALL_BUTTON_CLASS =
  'shrink-0 px-2 py-1.5 text-[10px] font-extrabold uppercase border-2 border-brutal-black dark:border-zinc-500 bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 disabled:opacity-40';

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
  const nameRef = useRef<HTMLInputElement | null>(null);
  const directoryRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isImeComposing(e)) return;
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const focus = setTimeout(() => (canRename ? nameRef : directoryRef).current?.focus(), 0);
    return () => {
      document.removeEventListener('keydown', onKey);
      clearTimeout(focus);
    };
  }, [onClose, canRename]);

  const browse = async () => {
    try {
      const selected = await pickHostDirectory({ multiple: false });
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (path) setWorkingDirectory(path);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  };

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
            <label
              htmlFor="project-settings-working-directory"
              className="block text-[10px] font-extrabold uppercase tracking-wide text-brutal-black dark:text-white"
            >
              {t('projectSettings.workingDirectory')}
            </label>
            <div className="flex items-stretch gap-1">
              <input
                id="project-settings-working-directory"
                ref={directoryRef}
                value={workingDirectory}
                placeholder={t('projectSettings.workingDirectoryPlaceholder')}
                onChange={(event) => setWorkingDirectory(event.target.value)}
                spellCheck={false}
                className={`${INPUT_CLASS} font-mono`}
              />
              <button type="button" onClick={browse} className={SMALL_BUTTON_CLASS}>
                {t('projectSettings.browse')}
              </button>
              <button
                type="button"
                onClick={() => setWorkingDirectory('')}
                disabled={!workingDirectory}
                className={SMALL_BUTTON_CLASS}
              >
                {t('projectSettings.clear')}
              </button>
            </div>
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
