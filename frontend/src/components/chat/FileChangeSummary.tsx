import React, { useEffect, useState } from 'react';
import {
  fetchChatFileChanges,
  undoChatFiles,
  type FileChangeSummaryResponse,
} from '../../lib/api';
import { useI18n } from '../../i18n';

export const FileChangeSummary: React.FC<{ chatId: string }> = ({ chatId }) => {
  const { t } = useI18n();
  const [summary, setSummary] = useState<FileChangeSummaryResponse | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchChatFileChanges(chatId)
      .then(data => {
        if (!cancelled) setSummary(data.files.length > 0 ? data : null);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => { cancelled = true; };
  }, [chatId]);

  if (!summary) return null;

  const undo = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await undoChatFiles(chatId);
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
    <div className="mt-3 border-2 border-brutal-black bg-white shadow-[3px_3px_0_0_#000] dark:border-zinc-500 dark:bg-zinc-900 dark:shadow-none">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
        <span className="font-bold">
          {t('fileChanges.editedFiles', { count: summary.files.length })}
        </span>
        <span className="font-mono text-green-600 dark:text-green-400">+{summary.additions}</span>
        <span className="font-mono text-red-600 dark:text-red-400">-{summary.deletions}</span>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => setReviewing(value => !value)}
            className="font-bold underline underline-offset-2"
          >
            {reviewing ? t('fileChanges.hideReview') : t('fileChanges.review')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={undo}
            className="font-bold text-brutal-red disabled:opacity-50"
          >
            {busy ? t('fileChanges.undoing') : t('fileChanges.undo')}
          </button>
        </div>
      </div>
      {message && (
        <div className="border-t-2 border-brutal-black px-3 py-2 text-xs dark:border-zinc-500">
          {message}
        </div>
      )}
      {reviewing && (
        <div className="max-h-96 overflow-auto border-t-2 border-brutal-black dark:border-zinc-500">
          {summary.files.map(file => (
            <details key={file.path} open className="border-b border-neutral-200 last:border-b-0 dark:border-zinc-700">
              <summary className="cursor-pointer px-3 py-2 font-mono text-xs font-bold">
                {file.path} <span className="text-green-600">+{file.additions}</span>{' '}
                <span className="text-red-600">-{file.deletions}</span>
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
