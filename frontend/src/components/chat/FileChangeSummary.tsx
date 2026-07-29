import React, { useEffect, useMemo, useRef, useState } from 'react';
import { undoChatFiles } from '../../lib/api';
import { parseUnifiedDiff } from '../../lib/unifiedDiff';
import type { MessageFileChange } from '../../types/api';
import { useI18n } from '../../i18n';
import { FileContentDiffViewer } from './FileDiffViewer';

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

const getDisplayPath = (file: MessageFileChange): string => {
  const path = (file.display_path || file.path).replace(/\\/g, '/');
  const sandboxMatch = path.match(/\/sandbox\/projects\/[^/]+\/(.+)$/);
  return sandboxMatch?.[1] || path;
};

interface FileChangeSummaryProps {
  chatId: string;
  messageIndex: number;
  files: MessageFileChange[];
  initiallyUndone?: boolean;
}

export const FileChangeSummary: React.FC<FileChangeSummaryProps> = ({
  chatId,
  messageIndex,
  files,
  initiallyUndone = false,
}) => {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [selectedPath, setSelectedPath] = useState(files[0]?.path ?? '');
  const [busy, setBusy] = useState(false);
  const [undoCompleted, setUndoCompleted] = useState(initiallyUndone);
  const [message, setMessage] = useState<string | null>(null);
  const undoStartedRef = useRef(initiallyUndone);
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
  const selectedFile = files.find(file => file.path === selectedPath) ?? files[0];
  const selectedDiff = useMemo(
    () => parseUnifiedDiff(selectedFile?.diff ?? ''),
    [selectedFile],
  );

  useEffect(() => {
    if (!files.some(file => file.path === selectedPath)) {
      setSelectedPath(files[0]?.path ?? '');
    }
  }, [files, selectedPath]);

  if (files.length === 0) return null;

  const undo = async (): Promise<void> => {
    if (undoStartedRef.current) return;
    undoStartedRef.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const result = await undoChatFiles(chatId, messageIndex);
      setUndoCompleted(true);
      setMessage(
        result.changed_files.length > 0
          ? t('fileChanges.undoSuccess', { count: result.changed_files.length })
          : t('fileChanges.undoNoChanges'),
      );
    } catch (error) {
      undoStartedRef.current = false;
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
    <div className="mt-3 overflow-hidden border-2 border-brutal-black bg-white text-brutal-black dark:border-zinc-500 dark:bg-zinc-900 dark:text-white">
      <div className="flex items-center gap-3 px-3 py-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-brutal-black bg-brutal-yellow text-brutal-black dark:border-zinc-300">
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
            disabled={busy || undoCompleted}
            onClick={undo}
            className="inline-flex items-center gap-1 px-2 py-1.5 text-sm font-bold text-brutal-black hover:bg-neutral-100 disabled:opacity-50 dark:text-white dark:hover:bg-zinc-800"
          >
            {busy
              ? t('fileChanges.undoing')
              : undoCompleted
                ? t('fileChanges.undone')
                : t('fileChanges.undo')}
            <UndoIcon />
          </button>
          <button
            type="button"
            aria-expanded={reviewing}
            onClick={() => setReviewing(value => !value)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm font-black transition-colors ${
              reviewing
                ? 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black'
                : 'text-brutal-black hover:bg-brutal-yellow/40 dark:text-white dark:hover:bg-zinc-800'
            }`}
          >
            {t('fileChanges.diff')}
            <ChevronIcon expanded={reviewing} />
          </button>
        </div>
      </div>

      <div className="border-t-2 border-brutal-black py-1 dark:border-zinc-500">
        {visibleFiles.map(file => (
          <button
            key={file.path}
            type="button"
            onClick={() => {
              setSelectedPath(file.path);
              setReviewing(true);
            }}
            className={`flex w-full min-w-0 items-center gap-3 border-l-4 px-3 py-1.5 text-left text-xs transition-colors ${
              reviewing && selectedFile?.path === file.path
                ? 'border-brutal-black bg-brutal-yellow/25 dark:border-brutal-yellow dark:bg-brutal-yellow/10'
                : 'border-transparent hover:bg-neutral-100 dark:hover:bg-zinc-800'
            }`}
          >
            <span className="min-w-0 flex-1 truncate font-mono font-bold text-neutral-600 dark:text-neutral-300">
              {getDisplayPath(file)}
            </span>
            <span className="shrink-0 font-mono">
              <span className="text-emerald-600 dark:text-emerald-400">+{file.additions}</span>{' '}
              <span className="text-red-500 dark:text-red-400">-{file.deletions}</span>
            </span>
          </button>
        ))}
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(value => !value)}
            className="ml-3 inline-flex items-center gap-1 py-1.5 text-xs font-black text-brutal-black hover:underline dark:text-white"
          >
            {expanded
              ? t('fileChanges.showLess')
              : t('fileChanges.showMore', { count: hiddenCount })}
            <ChevronIcon expanded={expanded} />
          </button>
        )}
      </div>

      {message && (
        <div className="border-t-2 border-brutal-black bg-brutal-yellow/20 px-3 py-2 text-xs font-bold dark:border-zinc-500">
          {message}
        </div>
      )}
      {reviewing && selectedFile && (
        <div className="border-t-2 border-brutal-black dark:border-zinc-500">
          {selectedDiff ? (
            <FileContentDiffViewer
              filePath={getDisplayPath(selectedFile)}
              original={selectedDiff.original}
              modified={selectedDiff.modified}
              addedLines={selectedFile.additions}
              removedLines={selectedFile.deletions}
              embedded
              showFullPath
            />
          ) : (
            <div className="bg-neutral-50 px-3 py-5 text-center text-xs font-bold text-neutral-500 dark:bg-zinc-950 dark:text-neutral-400">
              {t('fileChanges.binaryDiff')}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
