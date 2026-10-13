import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  ArrowUturnLeftIcon,
  CheckIcon,
  ChevronDownIcon,
  DocumentTextIcon,
  EyeIcon,
} from '@heroicons/react/24/outline';
import { undoChatFiles } from '../../lib/api';
import { parseUnifiedDiff } from '../../lib/unifiedDiff';
import type { MessageFileChange } from '../../types/api';
import { useI18n } from '../../i18n';
import { FileContentDiffViewer } from './FileDiffViewer';

const DEFAULT_VISIBLE_FILES = 3;

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
  const diffPanelId = useId();
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [selectedPath, setSelectedPath] = useState(files[0]?.path ?? '');
  const [busy, setBusy] = useState(false);
  const [undoCompleted, setUndoCompleted] = useState(initiallyUndone);
  const [message, setMessage] = useState<string | null>(null);
  const undoStartedRef = useRef(initiallyUndone);
  const additions = useMemo(
    () => files.reduce((total, file) => total + file.additions, 0),
    [files]
  );
  const deletions = useMemo(
    () => files.reduce((total, file) => total + file.deletions, 0),
    [files]
  );
  const visibleFiles = expanded ? files : files.slice(0, DEFAULT_VISIBLE_FILES);
  const hiddenCount = Math.max(0, files.length - DEFAULT_VISIBLE_FILES);
  const selectedFile = files.find((file) => file.path === selectedPath) ?? files[0];
  const selectedDiff = useMemo(() => parseUnifiedDiff(selectedFile?.diff ?? ''), [selectedFile]);

  const openDiffForFile = (file: MessageFileChange): void => {
    const isCurrentOpen = reviewing && selectedFile?.path === file.path;
    setSelectedPath(file.path);
    setReviewing(!isCurrentOpen);
  };

  const openFilePreview = (file: MessageFileChange, shiftKey = false): void => {
    onFileClick?.(file.path, getFileName(file), shiftKey);
  };

  useEffect(() => {
    if (!files.some((file) => file.path === selectedPath)) {
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
          : t('fileChanges.undoNoChanges')
      );
    } catch (error) {
      undoStartedRef.current = false;
      const conflicts = (error as Error & { conflicts?: string[] }).conflicts;
      setMessage(
        conflicts?.length
          ? t('fileChanges.conflict', { files: conflicts.join(', ') })
          : (error as Error).message
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="min-w-0 overflow-hidden border border-neutral-300 bg-white shadow-[2px_2px_0_0_rgba(0,0,0,0.06)] text-neutral-800 dark:border-zinc-600 dark:bg-zinc-900 dark:shadow-none dark:text-neutral-200">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-neutral-200 bg-neutral-100/70 px-3 py-1.5 dark:border-zinc-700 dark:bg-white/[0.035]">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="break-normal text-xs font-bold">
            {t(files.length === 1 ? 'fileChanges.changedFile' : 'fileChanges.changedFiles', {
              count: files.length,
            })}
          </span>
          {files.length > 1 && (
            <span className="flex gap-1.5 whitespace-nowrap font-mono text-[11px] tabular-nums">
              <span className="text-emerald-700 dark:text-emerald-400">+{additions}</span>
              <span className="text-red-600 dark:text-red-400">−{deletions}</span>
            </span>
          )}
        </div>
        <button
          type="button"
          disabled={busy || undoCompleted}
          onClick={undo}
          className="inline-flex min-h-7 shrink-0 items-center gap-1.5 px-1.5 text-[11px] font-bold text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-neutral-500 disabled:cursor-default disabled:opacity-50 dark:text-neutral-400 dark:hover:bg-white/5 dark:hover:text-neutral-200"
        >
          {undoCompleted ? (
            <CheckIcon className="h-3.5 w-3.5" />
          ) : (
            <ArrowUturnLeftIcon className="h-3.5 w-3.5" />
          )}
          <span className="whitespace-nowrap">
            {busy
              ? t('fileChanges.undoing')
              : undoCompleted
                ? t('fileChanges.undone')
                : t('fileChanges.undo')}
          </span>
        </button>
      </div>

      <div className="divide-y divide-neutral-100 dark:divide-zinc-800">
        {visibleFiles.map((file) => {
          const displayPath = getDisplayPath(file);
          const fileName = getFileName(file);
          const directory = displayPath.slice(0, displayPath.lastIndexOf('/') + 1);
          const isOpen = reviewing && selectedFile?.path === file.path;
          return (
            <div
              key={file.path}
              className={`flex min-w-0 items-center gap-1 px-2 py-1 ${isOpen ? 'bg-neutral-100/70 dark:bg-white/[0.04]' : ''}`}
            >
              <button
                type="button"
                onClick={() => openDiffForFile(file)}
                title={displayPath}
                aria-label={t('fileChanges.reviewFile', { file: fileName })}
                aria-expanded={isOpen}
                aria-controls={isOpen ? diffPanelId : undefined}
                className="group flex min-w-0 flex-1 items-center gap-2 px-1 py-2 text-left transition-colors hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-500 dark:hover:bg-white/[0.04]"
              >
                <DocumentTextIcon className="h-4 w-4 shrink-0 text-neutral-400 dark:text-neutral-500" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-mono text-xs font-semibold leading-5">
                    {fileName}
                  </span>
                  {directory && (
                    <span className="block truncate font-mono text-[10px] leading-4 text-neutral-500 dark:text-neutral-400">
                      {directory}
                    </span>
                  )}
                  <span className="mt-0.5 flex flex-wrap gap-x-2 font-mono text-[11px] leading-4 tabular-nums">
                    <span className="text-emerald-700 dark:text-emerald-400">
                      +{file.additions}
                    </span>
                    <span className="text-red-600 dark:text-red-400">−{file.deletions}</span>
                  </span>
                </span>
                <ChevronDownIcon
                  className={`h-3.5 w-3.5 shrink-0 text-neutral-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {onFileClick && (
                <button
                  type="button"
                  onClick={(event) => openFilePreview(file, event.shiftKey)}
                  title={t('fileChanges.openFile')}
                  aria-label={t('fileChanges.openFile')}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-500 dark:hover:bg-white/5 dark:hover:text-neutral-200"
                >
                  <EyeIcon className="h-4 w-4" />
                </button>
              )}
            </div>
          );
        })}
      </div>
      {hiddenCount > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="flex w-full items-center justify-center gap-1 border-t border-neutral-100 px-3 py-2 text-[11px] font-medium text-neutral-500 hover:bg-neutral-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-500 dark:border-zinc-800 dark:text-neutral-400 dark:hover:bg-white/[0.03]"
        >
          {expanded
            ? t('fileChanges.showLess')
            : t(hiddenCount === 1 ? 'fileChanges.showOneMore' : 'fileChanges.showMore', {
                count: hiddenCount,
              })}
          <ChevronDownIcon
            className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
          />
        </button>
      )}
      {message && (
        <div
          role="status"
          className="break-words border-t border-neutral-200 px-3 py-2 text-xs leading-relaxed text-neutral-500 dark:border-zinc-700 dark:text-neutral-400"
        >
          {message}
        </div>
      )}
      {reviewing && selectedFile && (
        <div id={diffPanelId} className="min-w-0 border-t border-neutral-200 dark:border-zinc-700">
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
            <div className="px-3 py-5 text-center text-xs text-neutral-500 dark:text-neutral-400">
              {t('fileChanges.binaryDiff')}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
