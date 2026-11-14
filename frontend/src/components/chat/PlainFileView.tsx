import React from 'react';
import { useI18n } from '../../i18n';
import { useOpenFile } from './openFileContext';

interface PlainFileViewProps {
  filePath: string;
  /** Short note beside the file name, such as the line range. */
  label?: string;
  /** Line numbers, one per line of `text`. */
  gutter: string;
  text: string;
}

/**
 * File text with a line-number gutter, as plain DOM rather than a Monaco
 * editor: cheap enough for every read and new-file write in a long chat.
 */
export const PlainFileView: React.FC<PlainFileViewProps> = ({ filePath, label, gutter, text }) => {
  const { t } = useI18n();
  const openFile = useOpenFile();
  const fileName = filePath.split(/[/\\]/).filter(Boolean).pop() || filePath;

  return (
    <div className="w-full min-w-0 overflow-hidden rounded-sm bg-neutral-50/70 dark:bg-zinc-800/40">
      <div className="flex min-w-0 items-center gap-2 border-b border-neutral-200/70 px-2.5 py-1 font-mono text-[11px] text-neutral-500 dark:border-zinc-700/70 dark:text-neutral-400">
        {openFile && filePath ? (
          <button
            type="button"
            onClick={(event) => openFile(filePath, fileName, event.shiftKey)}
            className="min-w-0 cursor-pointer truncate text-left text-neutral-700 decoration-1 underline-offset-2 hover:underline dark:text-neutral-200"
            title={`${t('toolCallBlock.openInPreview')} · ${filePath}`}
          >
            {fileName}
          </button>
        ) : (
          <span
            className="min-w-0 truncate text-neutral-700 dark:text-neutral-200"
            title={filePath}
          >
            {fileName}
          </span>
        )}
        {label && <span className="shrink-0">{label}</span>}
      </div>
      {/* One scroll container for both columns. The global `pre` rule sets
          overflow-x: auto, which makes each pre its own scroll box, so the
          gutter scrolled (and showed a scrollbar) on its own. */}
      <div className="flex max-h-[360px] min-w-0 items-start overflow-auto scrollbar-thin font-mono text-[12px] leading-5">
        <pre
          aria-hidden="true"
          className="m-0 shrink-0 select-none overflow-visible border-r border-neutral-200/70 py-1.5 pl-2.5 pr-2 text-right text-neutral-400 dark:border-zinc-700/70 dark:text-neutral-500"
        >
          {gutter}
        </pre>
        <pre className="m-0 min-w-0 flex-1 overflow-visible py-1.5 pl-2.5 pr-2.5 text-neutral-700 dark:text-neutral-200">
          {text}
        </pre>
      </div>
    </div>
  );
};
