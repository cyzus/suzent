import React, { useMemo } from 'react';
import { useI18n } from '../../i18n';
import type { ToolRendererProps } from './ToolCallBlock';
import { fileToolPath, parseReadFileOutput } from '../../lib/fileToolPreview';
import { PlainFileView } from './PlainFileView';

/**
 * read_file output as plain text with the file's own line numbers. It used to
 * mount a Monaco editor (a 2.6MB chunk, plus a language worker for TS/JS) and
 * renumbered every read from 1, so a read of lines 500-600 showed 1-100.
 */
export const ReadFileRenderer: React.FC<ToolRendererProps> = ({ parsedArgs, metadata, output }) => {
  const { t } = useI18n();
  const parsed = useMemo(() => (output ? parseReadFileOutput(output) : null), [output]);
  const filePath = fileToolPath(parsedArgs, metadata);

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
    <PlainFileView
      filePath={filePath}
      label={t('toolCallBlock.readFileRange', {
        start: parsed.start,
        end: parsed.end,
        total: parsed.total,
      })}
      gutter={parsed.gutter}
      text={parsed.text}
    />
  );
};
