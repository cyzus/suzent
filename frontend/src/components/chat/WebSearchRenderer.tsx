import React from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';

interface WebSearchRendererProps {
  output: string;
}

interface SearchResult {
  title: string;
  url: string;
  description: string;
  sources?: string;
}

export const WebSearchRenderer: React.FC<WebSearchRendererProps> = ({ output }) => {
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
          // Inner message is not JSON, might be raw text
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
      <div className="text-[11px] bg-neutral-50 dark:bg-zinc-800/50 p-2 border border-neutral-200 dark:border-zinc-700/50 rounded-sm">
        <MarkdownRenderer content={output} streamingLite={true} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 font-brutal">
      <div className="flex items-center gap-1.5 mb-1 pl-0.5">
        <span className="text-[10px] font-black text-brutal-black uppercase tracking-widest bg-white border-2 border-brutal-black px-2 py-0.5">
          Sources via {source}
        </span>
        <span className="text-[10px] font-mono font-bold text-brutal-black bg-brutal-yellow border-2 border-brutal-black px-2 py-0.5">
          {results.length} results
        </span>
      </div>
      
      <div className="grid grid-cols-1 gap-3 p-1.5 pr-2 pb-2">
        {results.map((result, i) => (
          <a
            key={i}
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block bg-white dark:bg-zinc-800 border-2 border-brutal-black p-2.5 hover:-translate-y-[2px] hover:-translate-x-[2px] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:bg-brutal-yellow/10 dark:hover:bg-brutal-yellow/20 transition-all cursor-pointer group"
          >
            <div className="flex justify-between items-start gap-4 mb-1">
              <h4 className="text-[13px] font-bold text-blue-700 dark:text-blue-400 group-hover:underline tracking-wide line-clamp-2">
                {result.title}
              </h4>
            </div>
            
            <div className="mb-1.5 flex items-center gap-1 text-[10px] font-mono font-semibold text-green-700 dark:text-green-400 truncate w-full">
              <svg className="w-3 h-3 stroke-[3] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              <span className="truncate max-w-[90%]">{result.url}</span>
            </div>
            
            <p className="text-[11px] font-medium text-neutral-800 dark:text-neutral-200 line-clamp-3 leading-relaxed font-sans mt-1">
              {result.description}
            </p>
            
            {result.sources && (
              <div className="mt-2 text-[9px] text-neutral-500 font-mono font-bold flex gap-1 items-center">
                <span className="uppercase leading-none">Engines:</span> 
                <span>{result.sources}</span>
              </div>
            )}
          </a>
        ))}
      </div>
    </div>
  );
};
