import React, { useMemo } from 'react';
import { useI18n } from '../../i18n';
import type { ToolRendererProps } from './ToolCallBlock';
import { fileToolPath, parseReadFileOutput } from '../../lib/fileToolPreview';
import { useOpenFile } from './openFileContext';

/**
 * read_file output as plain text with the file's own line numbers. It used to
 * mount a Monaco editor (a 2.6MB chunk, plus a language worker for TS/JS) and
 * renumbered every read from 1, so a read of lines 500-600 showed 1-100.
 */
export const ReadFileRenderer: React.FC<ToolRendererProps> = ({ parsedArgs, metadata, output }) => {
  const { t } = useI18n();
  const openFile = useOpenFile();
  const parsed = useMemo(() => (output ? parseReadFileOutput(output) : null), [output]);
  const filePath = fileToolPath(parsedArgs, metadata);
  const fileName = filePath.split(/[/\\]/).filter(Boolean).pop() || filePath;

  if (!parsed) {
    return (
      <div className="max-h-[320px] w-full overflow-y-auto overflow-x-hidden rounded-sm bg-neutral-50/70 px-2.5 py-2 scrollbar-thin dark:bg-zinc-800/40">
        <pre className="tool-call-pre m-0 w-full font-mono text-[12px] leading-5 text-neutral-600 dark:text-neutral-300">
          {output || '(no preview available)'}
        </pre>
      </div>
    );
  }

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
        <span className="shrink-0">
          {t('toolCallBlock.readFileRange', {
            start: parsed.start,
            end: parsed.end,
            total: parsed.total,
          })}
        </span>
      </div>
      <div className="flex max-h-[360px] min-w-0 overflow-auto scrollbar-thin font-mono text-[12px] leading-5">
        <pre
          aria-hidden="true"
          className="m-0 shrink-0 select-none border-r border-neutral-200/70 py-1.5 pl-2.5 pr-2 text-right text-neutral-400 dark:border-zinc-700/70 dark:text-neutral-500"
        >
          {parsed.gutter}
        </pre>
        <pre className="m-0 min-w-0 flex-1 py-1.5 pl-2.5 pr-2.5 text-neutral-700 dark:text-neutral-200">
          {parsed.text}
        </pre>
      </div>
    </div>
  );
};
