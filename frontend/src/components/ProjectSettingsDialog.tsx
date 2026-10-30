import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ClockIcon,
  FolderIcon,
  FolderPlusIcon,
  HomeIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { Project } from '../types/api';
import { useI18n } from '../i18n';
import { isImeComposing } from '../lib/ime';
import { getApiBase } from '../lib/api';
import { pickHostDirectory } from '../lib/hostPathPicker';
import { readFolderHistory, rememberFolders } from '../lib/folderHistory';

export interface ProjectSettingsUpdate {
  name?: string;
  workingDirectory?: string | null;
  extraFolders?: string[];
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

const SECTION_LABEL_CLASS =
  'block text-[10px] font-black uppercase tracking-wider text-neutral-500 dark:text-neutral-400';
const ADD_BUTTON_CLASS =
  'flex items-center justify-center gap-1.5 w-full px-3 py-2.5 text-xs font-black uppercase border-2 border-dashed border-brutal-black dark:border-zinc-500 text-brutal-black dark:text-white bg-white dark:bg-zinc-900 hover:bg-brutal-yellow/40 dark:hover:bg-zinc-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue';

const MAX_SUGGESTIONS = 5;

/** System projects keep their name. */
export const SYSTEM_PROJECT_SLUGS: ReadonlySet<string> = new Set(['default', 'social']);

const folderName = (path: string): string => path.split(/[/\\]/).filter(Boolean).pop() || path;

const sameFolders = (a: string[], b: string[]): boolean =>
  a.length === b.length && a.every((value, index) => value === b[index]);

/**
 * Per-project settings. The first folder is the project's working directory,
 * the default cwd for every chat in it; the other folders are mounted for those
 * chats. A chat that has its own working directory keeps it.
 */
export const ProjectSettingsDialog: React.FC<ProjectSettingsDialogProps> = ({
  project,
  canRename,
  onSave,
  onClose,
  rootDataAttrs,
}) => {
  const { t } = useI18n();
  const initialFolders = [
    ...(project.workingDirectory ? [project.workingDirectory] : []),
    ...(project.extraFolders ?? []).filter((path) => path !== project.workingDirectory),
  ];
  const [name, setName] = useState(project.name);
  const [folders, setFolders] = useState<string[]>(initialFolders);
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
  }, [onClose]);

  const addFolders = (paths: string[]) => {
    rememberFolders(paths);
    setFolders((prev) => [...prev, ...paths.filter((path) => path && !prev.includes(path))]);
  };
  const chooseFolders = async () => {
    try {
      const selected = await pickHostDirectory({ multiple: true });
      if (!selected) return;
      addFolders(Array.isArray(selected) ? selected : [selected]);
    } catch (err) {
      console.error('Failed to pick a host folder', err);
    }
  };

  // Folders to offer for adding: ones this project's chats used, then recent
  // picks from anywhere, leaving out what the project already has.
  const [recentFolders] = useState(() => readFolderHistory().map((item) => item.path));
  const suggestions = [
    ...projectFolders.map((path) => ({ path, recent: false })),
    ...recentFolders
      .filter((path) => !projectFolders.includes(path))
      .map((path) => ({ path, recent: true })),
  ]
    .filter(({ path }) => !folders.includes(path))
    .slice(0, MAX_SUGGESTIONS);
  const removeFolder = (index: number) => setFolders((prev) => prev.filter((_, i) => i !== index));
  const makePrimary = (index: number) =>
    setFolders((prev) => [prev[index], ...prev.filter((_, i) => i !== index)]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const update: ProjectSettingsUpdate = {};
    const trimmedName = name.trim();
    if (canRename && trimmedName && trimmedName !== project.name) update.name = trimmedName;
    if (!sameFolders(folders, initialFolders)) {
      update.workingDirectory = folders[0] ?? null;
      update.extraFolders = folders.slice(1);
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
        className="relative flex max-h-full w-full max-w-lg flex-col bg-white dark:bg-zinc-900 border-2 border-brutal-black dark:border-zinc-500 shadow-[6px_6px_0_0_#000] dark:shadow-[6px_6px_0_0_rgba(255,255,255,0.15)]"
      >
        <div className="flex items-start gap-3 px-5 py-4 border-b-2 border-brutal-black dark:border-zinc-500 bg-brutal-yellow dark:bg-zinc-800">
          <div className="min-w-0 flex-1">
            <h2
              id="project-settings-title"
              className="text-base font-black uppercase tracking-wide text-brutal-black dark:text-white"
            >
              {t('projectSettings.title')}
            </h2>
            <p className="mt-0.5 truncate text-xs font-bold text-brutal-black/70 dark:text-neutral-300">
              {project.name}
            </p>
          </div>
          <button
            type="button"
            aria-label={t('common.cancel')}
            onClick={onClose}
            className="-mr-1 p-1 text-brutal-black dark:text-white hover:bg-brutal-black/10 dark:hover:bg-white/10 transition-colors"
          >
            <XMarkIcon className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-5">
          {canRename && (
            <label className="block space-y-2">
              <span className={SECTION_LABEL_CLASS}>{t('projectSettings.name')}</span>
              <input
                ref={nameRef}
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="w-full min-w-0 px-3 py-2 text-sm font-bold bg-white dark:bg-zinc-800 dark:text-white border-2 border-brutal-black dark:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-brutal-blue"
              />
            </label>
          )}

          <section className="space-y-2">
            <div>
              <span className={SECTION_LABEL_CLASS}>{t('projectSettings.folders')}</span>
              <p className="mt-1 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400">
                {t('projectSettings.foldersHelp')}
              </p>
            </div>

            {folders.length === 0 ? (
              <p className="border-2 border-neutral-300 dark:border-zinc-700 bg-neutral-50 dark:bg-zinc-800/50 px-3 py-4 text-center text-xs text-neutral-500 dark:text-neutral-400">
                {t('projectSettings.noFolders')}
              </p>
            ) : (
              <ul className="border-2 border-brutal-black dark:border-zinc-500 divide-y-2 divide-brutal-black dark:divide-zinc-600">
                {folders.map((path, index) => {
                  const primary = index === 0;
                  return (
                    <li
                      key={path}
                      className={`group flex items-center gap-3 px-3 py-2.5 ${primary ? 'bg-brutal-yellow/30 dark:bg-zinc-800' : 'bg-white dark:bg-zinc-900'}`}
                    >
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center border-2 border-brutal-black dark:border-zinc-500 ${primary ? 'bg-brutal-yellow text-brutal-black' : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white'}`}
                      >
                        {primary ? (
                          <HomeIcon className="h-4 w-4" strokeWidth={2.5} />
                        ) : (
                          <FolderIcon className="h-4 w-4" strokeWidth={2} />
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-bold text-brutal-black dark:text-white">
                            {folderName(path)}
                          </span>
                          {primary && (
                            <span className="shrink-0 border border-brutal-black bg-brutal-black px-1.5 py-px text-[9px] font-black uppercase tracking-wide text-white dark:border-brutal-yellow dark:bg-brutal-yellow dark:text-brutal-black">
                              {t('projectSettings.workingDirectory')}
                            </span>
                          )}
                        </div>
                        <div
                          className="truncate font-mono text-[11px] text-neutral-500 dark:text-neutral-400"
                          title={path}
                          dir="rtl"
                        >
                          <bdi>{path}</bdi>
                        </div>
                      </div>
                      {!primary && (
                        <button
                          type="button"
                          onClick={() => makePrimary(index)}
                          className="shrink-0 px-2 py-1 text-[10px] font-black uppercase text-neutral-600 dark:text-neutral-300 opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 hover:bg-brutal-black hover:text-white dark:hover:bg-white dark:hover:text-brutal-black focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
                        >
                          {t('projectSettings.makePrimary')}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => removeFolder(index)}
                        aria-label={`${t('projectSettings.removeFolder')}: ${folderName(path)}`}
                        title={t('projectSettings.removeFolder')}
                        className="flex h-7 w-7 shrink-0 items-center justify-center text-neutral-500 dark:text-neutral-400 hover:bg-brutal-red hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
                      >
                        <XMarkIcon className="h-4 w-4" strokeWidth={2.5} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            {suggestions.length > 0 && (
              <div className="pt-2">
                <span className={SECTION_LABEL_CLASS}>{t('projectSettings.suggestions')}</span>
                <ul className="mt-1.5 divide-y divide-neutral-200 dark:divide-zinc-700 border-y border-neutral-200 dark:border-zinc-700">
                  {suggestions.map(({ path, recent }) => {
                    const Icon = recent ? ClockIcon : FolderIcon;
                    return (
                      <li key={path}>
                        <button
                          type="button"
                          onClick={() => addFolders([path])}
                          title={
                            recent
                              ? t('folderContext.recentFolders')
                              : t('folderContext.projectFolders')
                          }
                          className="group flex w-full items-center gap-2.5 px-1 py-2 text-left hover:bg-brutal-yellow/40 dark:hover:bg-zinc-800 focus:outline-none focus-visible:bg-brutal-yellow/40"
                        >
                          <Icon className="h-4 w-4 shrink-0 text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white" />
                          <span className="shrink-0 text-xs font-bold text-brutal-black dark:text-white">
                            {folderName(path)}
                          </span>
                          <span
                            className="min-w-0 flex-1 truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-400"
                            dir="rtl"
                          >
                            <bdi>{path}</bdi>
                          </span>
                          <PlusIcon
                            className="h-4 w-4 shrink-0 text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white"
                            strokeWidth={2.5}
                          />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <button type="button" onClick={chooseFolders} className={ADD_BUTTON_CLASS}>
              <FolderPlusIcon className="h-4 w-4" strokeWidth={2} />
              {suggestions.length > 0
                ? t('folderContext.chooseDifferent')
                : t('projectSettings.addFolder')}
            </button>

            <p className="text-[11px] leading-relaxed text-neutral-500 dark:text-neutral-400">
              {t('projectSettings.chatOverrideNote')}
            </p>
          </section>

          {error && (
            <p
              role="alert"
              className="border-2 border-brutal-red bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs font-bold text-brutal-red dark:text-red-400"
            >
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t-2 border-brutal-black dark:border-zinc-500 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-black uppercase tracking-wide text-brutal-black dark:text-zinc-200 hover:bg-neutral-100 dark:hover:bg-zinc-800"
          >
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2 text-xs font-black uppercase tracking-wide border-2 border-brutal-black bg-brutal-black text-white shadow-[3px_3px_0_0_#000] hover:bg-neutral-800 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none dark:border-brutal-yellow dark:bg-brutal-yellow dark:text-brutal-black dark:hover:bg-yellow-300 disabled:opacity-60"
          >
            {t('projectSettings.save')}
          </button>
        </div>
      </form>
    </div>
  );

  return createPortal(dialog, document.body);
};
