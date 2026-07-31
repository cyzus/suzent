import React, { useEffect, useMemo, useRef, useState } from 'react';
import { EyeIcon } from '@heroicons/react/24/outline';
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

const getFileName = (file: MessageFileChange): string => {
  const displayPath = getDisplayPath(file);
  return displayPath.split(/[/\\]/).filter(Boolean).pop() || displayPath || file.path;
};

interface FileChangeSummaryProps {
  chatId: string;
  messageIndex: number;
  files: MessageFileChange[];
  initiallyUndone?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}

export const FileChangeSummary: React.FC<FileChangeSummaryProps> = ({
  chatId,
  messageIndex,
  files,
  initiallyUndone = false,
  onFileClick,
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

  const openDiffForFile = (file: MessageFileChange): void => {
    const isCurrentOpen = reviewing && selectedFile?.path === file.path;
    setSelectedPath(file.path);
    setReviewing(!isCurrentOpen);
  };

  const openFilePreview = (file: MessageFileChange, shiftKey = false): void => {
    onFileClick?.(file.path, getFileName(file), shiftKey);
  };

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
    <div className="overflow-hidden border border-l-4 border-neutral-300 border-l-brutal-black bg-neutral-50/90 text-brutal-black dark:border-zinc-700 dark:border-l-zinc-500 dark:bg-white/[0.025] dark:text-white">
      <div className="flex items-center gap-2.5 border-b border-neutral-200 px-3 py-2 dark:border-zinc-700">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center bg-brutal-yellow/45 text-brutal-black dark:bg-white/10 dark:text-neutral-200">
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
            className="inline-flex items-center gap-1 px-2 py-1.5 text-sm font-bold text-brutal-black hover:bg-black/[0.05] disabled:opacity-40 dark:text-white dark:hover:bg-white/[0.07]"
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
                ? 'bg-black/[0.08] text-brutal-black dark:bg-white/10 dark:text-white'
                : 'text-brutal-black hover:bg-black/[0.05] dark:text-white dark:hover:bg-white/[0.07]'
            }`}
          >
            {t('fileChanges.diff')}
            <ChevronIcon expanded={reviewing} />
          </button>
        </div>
      </div>

      <div className="py-1">
        {visibleFiles.map(file => (
          <div
            key={file.path}
            className={`group/file-row flex w-full min-w-0 items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
              reviewing && selectedFile?.path === file.path
                ? 'bg-black/[0.055] dark:bg-white/[0.07]'
                : 'hover:bg-black/[0.035] dark:hover:bg-white/[0.05]'
            }`}
          >
            <button
              type="button"
              onClick={() => openDiffForFile(file)}
              className="flex min-w-0 flex-1 items-center gap-3 text-left"
              aria-expanded={reviewing && selectedFile?.path === file.path}
            >
              <span className="min-w-0 flex-1 truncate font-mono font-bold text-neutral-600 dark:text-neutral-300">
                {getDisplayPath(file)}
              </span>
            </button>
            <span className="shrink-0 font-mono font-bold">
              <span className="text-emerald-600 dark:text-emerald-400">+{file.additions}</span>{' '}
              <span className="text-red-500 dark:text-red-400">-{file.deletions}</span>
            </span>
            {onFileClick && (
              <button
                type="button"
                onClick={event => openFilePreview(file, event.shiftKey)}
                title={t('fileChanges.openFile')}
                aria-label={t('fileChanges.openFile')}
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center text-neutral-500 opacity-70 transition hover:bg-black/[0.06] hover:text-brutal-black group-hover/file-row:opacity-100 dark:text-neutral-400 dark:hover:bg-white/[0.08] dark:hover:text-white"
              >
                <EyeIcon className="h-4 w-4 stroke-[2.2]" />
              </button>
            )}
          </div>
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
        <div className="border-t border-neutral-300 bg-black/[0.025] px-3 py-2 text-xs font-bold dark:border-zinc-700 dark:bg-white/[0.035]">
          {message}
        </div>
      )}
      {reviewing && selectedFile && (
        <div className="border-t border-neutral-300 dark:border-zinc-700">
          {selectedDiff ? (
            <FileContentDiffViewer
              filePath={getDisplayPath(selectedFile)}
              original={selectedDiff.original}
              modified={selectedDiff.modified}
              addedLines={selectedFile.additions}
              removedLines={selectedFile.deletions}
              embedded
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
