import React from 'react';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';

interface WebSearchSidebarViewProps {
  output: string;
}

interface SearchResult {
  title: string;
  url: string;
  description: string;
  sources?: string;
}

export const WebSearchSidebarView: React.FC<WebSearchSidebarViewProps> = ({ output }) => {
  const parseResults = (): { source: string; results: SearchResult[]; isSuccess: boolean } => {
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
          data = { results: [] };
        }
      }

      if (data && data.results && Array.isArray(data.results)) {
        return { 
          source: data.source || 'Web Search', 
          results: data.results, 
          isSuccess: data.results.length > 0 
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
            sources: match[4]?.trim()
          });
        }

        return { source, results, isSuccess: results.length > 0 };
      } catch (fallbackError) {
        return { source: 'Web Search', results: [], isSuccess: false };
      }
    }
  };

  const { source, results, isSuccess } = parseResults();

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
      <div className="p-4 pb-2 sticky top-0 bg-neutral-50 dark:bg-zinc-900 z-10 border-b border-neutral-200 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <span className="text-xs font-black text-brutal-black dark:text-neutral-200 uppercase tracking-widest bg-white dark:bg-zinc-800 border-2 border-brutal-black dark:border-zinc-600 px-2 py-1">
            Results via {source}
          </span>
          <span className="text-xs font-mono font-bold text-brutal-black bg-brutal-yellow border-2 border-brutal-black px-2 py-1">
            {results.length} found
          </span>
        </div>
      </div>
      
      <div className="flex-1 p-4 pt-2">
        <div className="flex flex-col gap-4">
          {results.map((result, i) => (
            <a
              key={i}
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block bg-white dark:bg-zinc-800 border-2 border-brutal-black p-4 hover:-translate-y-[2px] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:bg-brutal-yellow/5 dark:hover:bg-brutal-yellow/10 transition-all cursor-pointer group"
            >
              <div className="flex justify-between items-start gap-4 mb-2">
                <h4 className="text-sm md:text-base font-bold text-blue-700 dark:text-blue-400 group-hover:underline tracking-wide line-clamp-2">
                  {result.title}
                </h4>
              </div>
              
              <div className="mb-2 flex items-center gap-1.5 text-xs font-mono font-semibold text-green-700 dark:text-green-400 truncate w-full">
                <svg className="w-3.5 h-3.5 stroke-[3] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                </svg>
                <span className="truncate max-w-[95%]">{result.url}</span>
              </div>
              
              <p className="text-xs md:text-sm font-medium text-neutral-800 dark:text-neutral-200 line-clamp-4 leading-relaxed font-sans mt-2">
                {result.description}
              </p>
              
              {result.sources && (
                <div className="mt-3 inline-flex text-[10px] text-neutral-600 dark:text-neutral-400 bg-neutral-100 dark:bg-zinc-700 px-2 py-0.5 font-mono font-bold items-center rounded-sm">
                  <span className="uppercase mr-1">Engine:</span> 
                  <span>{result.sources}</span>
                </div>
              )}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
};
