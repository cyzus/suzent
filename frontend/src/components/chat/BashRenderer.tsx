import React, { useMemo, useState, useCallback } from 'react';
import type { ToolRendererProps } from './ToolCallBlock';

export type BashRendererProps = ToolRendererProps;

const LANGUAGE_LABELS: Record<string, string> = {
  python: 'Python',
  nodejs: 'Node.js',
  command: 'Shell',
};

// Renders in the args section: command only, with copy button.
export const BashCommandRenderer: React.FC<BashRendererProps> = ({ parsedArgs }) => {
  const [copied, setCopied] = useState(false);

  const { command, langLabel } = useMemo(() => {
    const command = typeof parsedArgs?.content === 'string' ? parsedArgs.content : '';
    const rawLang = typeof parsedArgs?.language === 'string' ? parsedArgs.language : 'command';
    return { command, langLabel: LANGUAGE_LABELS[rawLang] ?? rawLang };
  }, [parsedArgs]);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [command]);

  return (
    <div className="flex items-start min-w-0 mt-1">
      <span className="w-14 shrink-0 text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase pt-[5px] pr-2 text-right select-none">
        {langLabel}
      </span>
      <div className="relative flex-1 min-w-0 group">
        <pre className="tool-call-pre font-mono text-[12px] leading-5 text-neutral-700 dark:text-neutral-200 bg-neutral-100 dark:bg-zinc-800 pl-2 pr-8 py-1.5 rounded-sm overflow-x-auto whitespace-pre-wrap break-all m-0">
          {command}
        </pre>
        <button
          onClick={handleCopy}
          className="absolute top-1 right-1 p-1 rounded-sm opacity-0 group-hover:opacity-100 transition-opacity text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
          title="Copy command"
        >
          {copied ? (
            <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
};

// Renders in the output section: stdout + exit code only.
export const BashOutputRenderer: React.FC<BashRendererProps> = ({ metadata, output }) => {
  const { returncode, outputText } = useMemo(() => {
    const returncode = typeof metadata?.returncode === 'number' ? metadata.returncode : null;
    const outputText = (output ?? '').replace(/^\[cwd:[^\]]*\]\n?/, '');
    return { returncode, outputText };
  }, [metadata, output]);

  const failed = returncode !== null && returncode !== 0;
  const outLabel = returncode !== null ? `exit ${returncode}` : 'out';

  return (
    <div className="flex items-start min-w-0">
      <span className={`w-14 shrink-0 text-[10px] font-mono font-bold uppercase pt-[5px] pr-2 text-right select-none ${failed ? 'text-red-500' : 'text-neutral-400 dark:text-neutral-500'}`}>
        {outLabel}
      </span>
      <pre className={`tool-call-pre flex-1 font-mono text-[12px] leading-5 px-2 py-1.5 rounded-sm overflow-x-auto max-h-[240px] overflow-y-auto whitespace-pre-wrap break-all m-0 ${failed ? 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30' : 'text-neutral-600 dark:text-neutral-300 bg-neutral-50 dark:bg-zinc-900'}`}>
        {outputText.trim() || '(no output)'}
      </pre>
    </div>
  );
};
