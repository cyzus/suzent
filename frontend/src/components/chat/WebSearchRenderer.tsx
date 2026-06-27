import React, { useState } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { useI18n } from '../../i18n';

interface WebSearchRendererProps {
  output: string;
}

interface SearchResult {
  title: string;
  url: string;
  description: string;
  sources?: string;
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

export function parseSearchResults(output: string): { source: string; results: SearchResult[]; isSuccess: boolean } {
  try {
    const parsedOutput = JSON.parse(output);

    // Check if it is a ToolResult envelope
    let data = parsedOutput;
    if (parsedOutput && typeof parsedOutput === 'object' && 'success' in parsedOutput && typeof parsedOutput.message === 'string') {
      if (!parsedOutput.success) {
        return { source: 'Web Search', results: [], isSuccess: false };
      }
      // Parse the inner JSON payload
      try {
        data = JSON.parse(parsedOutput.message);
      } catch (e) {
        // Inner message is not JSON, might be raw text
        data = { results: [] };
      }
    }

    if (data && data.results && Array.isArray(data.results)) {
      return {
        source: data.source || 'Web Search',
        results: data.results,
        isSuccess: data.results.length > 0,
      };
    }
    return { source: 'Web Search', results: [], isSuccess: false };
  } catch (e) {
    // Fallback for older markdown outputs
    try {
      const sourceMatch = output.match(/# Search Results \(via (.*)\)/);
      const source = sourceMatch ? sourceMatch[1] : 'Web Search';

      const results: SearchResult[] = [];
      const resultRegex = /## \d+\. (.*?)\n\*\*URL:\*\* (.*?)\n\*\*Description:\*\* (.*?)(?:\n\*\*Sources:\*\* (.*?))?(?=\n## \d+\. |\n*$)/gs;

      let match;
      while ((match = resultRegex.exec(output)) !== null) {
        results.push({
          title: match[1]?.trim() || '',
          url: match[2]?.trim() || '',
          description: match[3]?.trim() || '',
          sources: match[4]?.trim(),
        });
      }

      return { source, results, isSuccess: results.length > 0 };
    } catch (fallbackError) {
      return { source: 'Web Search', results: [], isSuccess: false };
    }
  }
}

export const WebSearchRenderer: React.FC<WebSearchRendererProps> = ({ output }) => {
  const { t } = useI18n();
  const { source, results, isSuccess } = parseSearchResults(output);

  // Fallback to MarkdownRenderer if parsing fails or no results (e.g. error messages)
  if (!isSuccess) {
    return (
      <div className="text-[11px] bg-neutral-50 dark:bg-zinc-800/50 p-2 border border-neutral-200 dark:border-zinc-700/50 rounded-sm">
        <MarkdownRenderer content={output} streamingLite={true} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5 font-brutal">
      <div className="flex items-center gap-1.5 pl-0.5">
        <span className="text-[10px] font-black text-brutal-black dark:text-neutral-100 uppercase tracking-widest bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500 px-2 py-0.5">
          {source}
        </span>
        <span className="text-[10px] font-mono font-bold text-brutal-black bg-brutal-yellow border-2 border-brutal-black px-2 py-0.5">
          {t(results.length === 1 ? 'toolCallBlock.resultOne' : 'toolCallBlock.resultMany', { count: results.length })}
        </span>
      </div>

      <div className="flex flex-col gap-2 p-1 pr-1.5 pb-1.5">
        {results.map((result, i) => (
          <a
            key={i}
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-500 p-2.5 no-underline shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:-translate-y-[2px] hover:-translate-x-[2px] hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:bg-brutal-yellow/10 dark:hover:bg-brutal-yellow/20 transition-all group"
          >
            <span className="flex items-center gap-1.5 min-w-0">
              <ResultFavicon url={result.url} className="w-3.5 h-3.5" />
              <span className="text-[10px] font-mono font-bold text-neutral-500 dark:text-neutral-400 truncate">
                {domainOf(result.url)}
              </span>
            </span>
            <span className="block mt-0.5 text-[13px] font-bold text-brutal-black dark:text-neutral-100 group-hover:underline tracking-wide line-clamp-2">
              {result.title}
            </span>
            <span className="block mt-1 text-[11px] font-medium text-neutral-700 dark:text-neutral-300 line-clamp-2 leading-relaxed font-sans">
              {result.description}
            </span>
            {result.sources && (
              <span className="block mt-1.5 text-[9px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase tracking-wide">
                {t('toolCallBlock.viaEngine', { engine: result.sources })}
              </span>
            )}
          </a>
        ))}
      </div>
    </div>
  );
};
