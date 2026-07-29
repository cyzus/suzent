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
    <div className="mt-3 overflow-hidden border-2 border-brutal-black bg-white text-brutal-black shadow-[3px_3px_0_0_#000] dark:border-white dark:bg-zinc-800 dark:text-white dark:shadow-[3px_3px_0_0_#fff]">
      <div className="flex items-center gap-3 px-3 py-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center border-2 border-brutal-black bg-brutal-yellow text-brutal-black dark:border-white">
          <FileChangesIcon />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-black text-brutal-black dark:text-white">
            {t('fileChanges.editedFiles', { count: files.length })}
          </div>
          <div className="font-mono text-xs font-bold">
            <span className="text-emerald-600 dark:text-emerald-400">+{additions}</span>{' '}
            <span className="text-red-500 dark:text-red-400">-{deletions}</span>
          </div>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={undo}
            className="inline-flex items-center gap-1 px-2 py-1.5 text-sm font-bold text-brutal-black hover:bg-neutral-100 disabled:opacity-50 dark:text-white dark:hover:bg-zinc-700"
          >
            {busy ? t('fileChanges.undoing') : t('fileChanges.undo')}
            <UndoIcon />
          </button>
          <button
            type="button"
            onClick={() => setReviewing(value => !value)}
            className="border-2 border-brutal-black bg-white px-3 py-1 text-sm font-bold text-brutal-black shadow-[2px_2px_0_0_#000] hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_#000] dark:border-white dark:bg-zinc-800 dark:text-white dark:shadow-[2px_2px_0_0_#fff]"
          >
            {reviewing ? t('fileChanges.hideReview') : t('fileChanges.review')}
          </button>
        </div>
      </div>

      <div className="border-t-2 border-brutal-black px-3 py-2 dark:border-white">
        {visibleFiles.map(file => (
          <div key={file.path} className="flex min-w-0 items-center gap-3 py-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate font-mono font-bold text-neutral-600 dark:text-neutral-300">
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
            className="inline-flex items-center gap-1 py-1.5 text-xs font-black text-brutal-black hover:underline dark:text-white"
          >
            {expanded
              ? t('fileChanges.showLess')
              : t('fileChanges.showMore', { count: hiddenCount })}
            <ChevronIcon expanded={expanded} />
          </button>
        )}
      </div>

      {message && (
        <div className="border-t-2 border-brutal-black bg-brutal-yellow/20 px-3 py-2 text-xs font-bold dark:border-white">
          {message}
        </div>
      )}
      {reviewing && (
        <div className="max-h-96 overflow-auto border-t-2 border-brutal-black dark:border-white">
          {files.map(file => (
            <details key={file.path} className="border-b-2 border-brutal-black last:border-b-0 dark:border-white">
              <summary className="cursor-pointer bg-neutral-50 px-3 py-2 font-mono text-xs font-bold dark:bg-zinc-900">
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
