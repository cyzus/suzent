import React from 'react';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { CopyButton } from '../chat/CopyButton';

interface WebPageReaderViewProps {
  markdown: string;
  title?: string;
  url?: string;
}

export const WebPageReaderView: React.FC<WebPageReaderViewProps> = ({ markdown, title, url }) => {
  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900 border-l border-neutral-200 dark:border-zinc-800 font-sans w-full">
      {/* Header */}
      <div className="px-4 py-3 sticky top-0 bg-white/95 dark:bg-zinc-900/95 backdrop-blur-sm z-10 border-b border-neutral-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
        <div className="min-w-0 flex-1 pr-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-black text-brutal-black dark:text-neutral-200 uppercase tracking-widest bg-neutral-100 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-600 px-1.5 py-0.5 rounded-sm shrink-0">
              Web Page
            </span>
            <h3 className="text-sm font-bold text-neutral-800 dark:text-neutral-100 truncate">
              {title || 'Web Page Content'}
            </h3>
          </div>
          {url && (
            <div className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 font-mono">
              <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              <a href={url} target="_blank" rel="noopener noreferrer" className="truncate hover:underline">
                {url}
              </a>
            </div>
          )}
        </div>
        <CopyButton text={markdown} className="shrink-0" />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin w-full">
        <div className="max-w-3xl mx-auto prose dark:prose-invert prose-sm md:prose-base prose-pre:bg-neutral-50 dark:prose-pre:bg-zinc-800/50 prose-pre:border prose-pre:border-neutral-200 dark:prose-pre:border-zinc-700">
          <MarkdownRenderer content={markdown} />
        </div>
      </div>
    </div>
  );
};
