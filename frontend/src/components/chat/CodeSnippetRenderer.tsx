import React, { useMemo } from 'react';
import type { ToolRendererProps } from './ToolCallBlock';

// Renders in the args section of run_code: the Python snippet the model wrote.
// The calls it makes appear as their own tool rows below it.
export const CodeSnippetRenderer: React.FC<ToolRendererProps> = ({ parsedArgs }) => {
  const code = useMemo(
    () => (typeof parsedArgs?.code === 'string' ? parsedArgs.code : ''),
    [parsedArgs]
  );
  if (!code) return null;

  return (
    <div className="flex items-start min-w-0 mt-1">
      <span className="w-14 shrink-0 text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase pt-[5px] pr-2 text-right select-none">
        Python
      </span>
      <pre className="tool-call-pre flex-1 min-w-0 font-mono text-[12px] leading-5 text-neutral-700 dark:text-neutral-200 bg-neutral-100 dark:bg-zinc-800 px-2 py-1.5 rounded-sm overflow-x-auto whitespace-pre m-0">
        {code}
      </pre>
    </div>
  );
};
