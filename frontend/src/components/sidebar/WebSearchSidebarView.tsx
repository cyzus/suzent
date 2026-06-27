import React, { useState } from 'react';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { parseSearchResults } from '../chat/WebSearchRenderer';
import { useI18n } from '../../i18n';

interface WebSearchSidebarViewProps {
  output: string;
}

/** Hostname for a result url, stripped of a leading www. (e.g. "bbc.co.uk"). */
function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Favicon via Google's service, with a 🔗 fallback if it fails to load. */
const ResultFavicon: React.FC<{ url: string; className?: string }> = ({ url, className = 'w-4 h-4' }) => {
  const [failed, setFailed] = useState(false);
  const domain = domainOf(url);
  if (failed || !domain) {
    return <span className={`inline-flex items-center justify-center leading-none ${className}`}>🔗</span>;
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`}
      alt=""
      className={`${className} shrink-0 rounded-[2px] object-contain`}
      onError={() => setFailed(true)}
      loading="lazy"
    />
  );
};

export const WebSearchSidebarView: React.FC<WebSearchSidebarViewProps> = ({ output }) => {
  const { t } = useI18n();
  const { source, results, isSuccess } = parseSearchResults(output);

  // Fallback to MarkdownRenderer if parsing fails or no results (e.g. error messages)
  if (!isSuccess) {
    return (
      <div className="p-4 h-full overflow-y-auto">
        <div className="text-sm bg-neutral-50 dark:bg-zinc-800/50 p-4 border border-neutral-200 dark:border-zinc-700/50 rounded-sm">
          <MarkdownRenderer content={output} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-neutral-50 dark:bg-zinc-900 font-brutal overflow-y-auto w-full">
      <div className="p-4 pb-3 sticky top-0 bg-neutral-50 dark:bg-zinc-900 z-10 border-b-2 border-brutal-black dark:border-zinc-700">
        <div className="flex items-center gap-2">
          <span className="text-xs font-black text-brutal-black dark:text-neutral-100 uppercase tracking-widest bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500 px-2 py-1">
            {source}
          </span>
          <span className="text-xs font-mono font-bold text-brutal-black bg-brutal-yellow border-2 border-brutal-black px-2 py-1">
            {t(results.length === 1 ? 'toolCallBlock.resultOne' : 'toolCallBlock.resultMany', { count: results.length })}
          </span>
        </div>
      </div>

      <div className="flex-1 p-4 pt-3">
        <div className="flex flex-col gap-3">
          {results.map((result, i) => (
            <a
              key={i}
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500 p-3 no-underline shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:-translate-y-[2px] hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:bg-brutal-yellow/5 dark:hover:bg-brutal-yellow/10 transition-all group"
            >
              <span className="flex items-center gap-1.5 min-w-0">
                <ResultFavicon url={result.url} className="w-4 h-4" />
                <span className="text-[11px] font-mono font-bold text-neutral-500 dark:text-neutral-400 truncate">
                  {domainOf(result.url)}
                </span>
              </span>
              <span className="block mt-1 text-sm font-bold text-brutal-black dark:text-neutral-100 group-hover:underline tracking-wide line-clamp-2">
                {result.title}
              </span>
              <span className="block mt-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 line-clamp-4 leading-relaxed font-sans">
                {result.description}
              </span>
              {result.sources && (
                <span className="mt-2 inline-flex w-fit text-[10px] text-brutal-black dark:text-neutral-200 bg-neutral-100 dark:bg-zinc-700 border-2 border-brutal-black dark:border-zinc-500 px-2 py-0.5 font-mono font-bold uppercase tracking-wide">
                  {t('toolCallBlock.viaEngine', { engine: result.sources })}
                </span>
              )}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
};
