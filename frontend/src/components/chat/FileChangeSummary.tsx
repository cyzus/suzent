import React, { useMemo, useState } from 'react';
import { undoChatFiles } from '../../lib/api';
import type { MessageFileChange } from '../../types/api';
import { useI18n } from '../../i18n';

const DEFAULT_VISIBLE_FILES = 3;

const FileChangesIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <path d="M9 9h6M12 6v6M9 16h6" />
  </svg>
);

const UndoIcon: React.FC = () => (
  <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7">
    <path d="M7 6 4 9l3 3" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M5 9h6a4 4 0 1 1 0 8h-1" strokeLinecap="round" />
  </svg>
);

const ChevronIcon: React.FC<{ expanded: boolean }> = ({ expanded }) => (
  <svg
    viewBox="0 0 20 20"
    className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
  >
    <path d="m6 8 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

interface FileChangeSummaryProps {
  chatId: string;
  messageIndex: number;
  files: MessageFileChange[];
}

export const FileChangeSummary: React.FC<FileChangeSummaryProps> = ({
  chatId,
  messageIndex,
  files,
}) => {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const additions = useMemo(
    () => files.reduce((total, file) => total + file.additions, 0),
    [files],
  );
  const deletions = useMemo(
    () => files.reduce((total, file) => total + file.deletions, 0),
    [files],
  );
  const visibleFiles = expanded ? files : files.slice(0, DEFAULT_VISIBLE_FILES);
  const hiddenCount = Math.max(0, files.length - DEFAULT_VISIBLE_FILES);

  if (files.length === 0) return null;

  const undo = async (): Promise<void> => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await undoChatFiles(chatId, messageIndex);
      setMessage(t('fileChanges.undoSuccess', { count: result.changed_files.length }));
    } catch (error) {
      const conflicts = (error as Error & { conflicts?: string[] }).conflicts;
      setMessage(
        conflicts?.length
          ? t('fileChanges.conflict', { files: conflicts.join(', ') })
          : (error as Error).message,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-neutral-200 bg-white text-neutral-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-neutral-200">
      <div className="flex items-center gap-3 px-3 py-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-neutral-600 dark:bg-zinc-800 dark:text-neutral-300">
          <FileChangesIcon />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">
            {t('fileChanges.editedFiles', { count: files.length })}
          </div>
          <div className="font-mono text-xs">
            <span className="text-emerald-600 dark:text-emerald-400">+{additions}</span>{' '}
            <span className="text-red-500 dark:text-red-400">-{deletions}</span>
          </div>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={undo}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-neutral-700 hover:bg-neutral-100 disabled:opacity-50 dark:text-neutral-200 dark:hover:bg-zinc-800"
          >
            {busy ? t('fileChanges.undoing') : t('fileChanges.undo')}
            <UndoIcon />
          </button>
          <button
            type="button"
            onClick={() => setReviewing(value => !value)}
            className="rounded-xl border border-neutral-200 px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-50 dark:border-zinc-700 dark:text-neutral-200 dark:hover:bg-zinc-800"
          >
            {reviewing ? t('fileChanges.hideReview') : t('fileChanges.review')}
          </button>
        </div>
      </div>

      <div className="border-t border-neutral-200 px-3 py-2 dark:border-zinc-700">
        {visibleFiles.map(file => (
          <div key={file.path} className="flex min-w-0 items-center gap-3 py-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate font-mono text-neutral-500 dark:text-neutral-400">
              {file.display_path || file.path}
            </span>
            <span className="shrink-0 font-mono">
              <span className="text-emerald-600 dark:text-emerald-400">+{file.additions}</span>{' '}
              <span className="text-red-500 dark:text-red-400">-{file.deletions}</span>
            </span>
          </div>
        ))}
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(value => !value)}
            className="inline-flex items-center gap-1 py-1.5 text-xs font-medium text-neutral-700 hover:text-neutral-950 dark:text-neutral-300 dark:hover:text-white"
          >
            {expanded
              ? t('fileChanges.showLess')
              : t('fileChanges.showMore', { count: hiddenCount })}
            <ChevronIcon expanded={expanded} />
          </button>
        )}
      </div>

      {message && (
        <div className="border-t border-neutral-200 px-3 py-2 text-xs dark:border-zinc-700">
          {message}
        </div>
      )}
      {reviewing && (
        <div className="max-h-96 overflow-auto border-t border-neutral-200 dark:border-zinc-700">
          {files.map(file => (
            <details key={file.path} className="border-b border-neutral-100 last:border-b-0 dark:border-zinc-800">
              <summary className="cursor-pointer px-3 py-2 font-mono text-xs font-medium">
                {file.display_path || file.path}
              </summary>
              <pre className="overflow-x-auto bg-neutral-50 px-3 py-2 text-[11px] leading-5 dark:bg-zinc-950">
                {file.diff || t('fileChanges.binaryDiff')}
              </pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
};
