import React, { useState } from 'react';
import { FolderOpenIcon } from '@heroicons/react/24/outline';
import { FileIcon } from '../FileIcon';
import { getApiBase } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { useI18n } from '../../i18n';

const MIME_BY_EXTENSION: Record<string, string> = {
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  csv: 'text/csv',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  zip: 'application/zip',
  md: 'text/markdown',
  txt: 'text/plain',
};

/** A file the agent handed over with send_file that isn't an image, video or audio. */
export function SentFileCard({ path }: { path: string }): React.ReactElement {
  const { t } = useI18n();
  const { currentChatId } = useChatStore();
  const [revealFailed, setRevealFailed] = useState(false);
  const name = path.split(/[\\/]/).pop() || path;
  const extension = name.includes('.') ? name.split('.').pop()!.toLowerCase() : '';

  const reveal = async (): Promise<void> => {
    setRevealFailed(false);
    try {
      const response = await fetch(`${getApiBase()}/system/open_explorer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, chat_id: currentChatId }),
      });
      if (!response.ok) setRevealFailed(true);
    } catch {
      setRevealFailed(true);
    }
  };

  return (
    <div className="w-full max-w-md border border-neutral-200 bg-white dark:border-zinc-700 dark:bg-zinc-800">
      <div className="flex items-center gap-3 px-3 py-2">
        <FileIcon
          mimeType={MIME_BY_EXTENSION[extension] ?? 'application/octet-stream'}
          className="h-5 w-5 shrink-0 text-neutral-500 dark:text-neutral-400"
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium" title={path}>
            {name}
          </span>
          <span className="block text-[11px] text-neutral-500 dark:text-neutral-400">
            {t('sentFile.label')}
          </span>
        </span>
        <button
          type="button"
          onClick={() => void reveal()}
          title={t('sentFile.reveal')}
          aria-label={t('sentFile.reveal')}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-500 dark:hover:bg-white/5 dark:hover:text-neutral-200"
        >
          <FolderOpenIcon className="h-4 w-4" />
        </button>
      </div>
      {revealFailed && (
        <p role="alert" className="px-3 pb-2 text-xs text-brutal-red">
          {t('sandbox.contextMenu.revealFailed')}
        </p>
      )}
    </div>
  );
}
