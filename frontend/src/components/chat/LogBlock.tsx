import React, { useState } from 'react';
import { useStatusStore } from '../../hooks/useStatusStore';

interface LogBlockProps {
  title?: string;
  content: string;
}

export const LogBlock: React.FC<LogBlockProps> = ({ title, content }) => {
  const [expanded, setExpanded] = useState(() => {
    return content.length < 300 && content.split('\n').length <= 5;
  });
  const { setStatus } = useStatusStore();
  const [copied, setCopied] = useState(false);
  const lineCount = content.split('\n').length;

  const copyToClipboard = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(content);
    setStatus('LOG_COPIED_TO_CLIPBOARD', 'success');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-6 font-mono text-sm border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] bg-white group">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-brutal-black border-b-3 border-brutal-black select-none overflow-hidden">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="flex items-center justify-center w-6 h-6 bg-white border-2 border-white text-brutal-black font-bold text-xs shrink-0">
            <span>{'>_'}</span>
          </div>
          <span className="text-white font-bold uppercase tracking-wider text-xs truncate">
            {title || 'System Log'}
          </span>
          <span className="text-neutral-400 text-[10px] font-bold shrink-0">
            {lineCount} LINES
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={copyToClipboard}
            className="w-8 h-8 flex items-center justify-center bg-brutal-black text-white border-2 border-white hover:bg-white hover:text-brutal-black transition-colors"
            title="Copy to clipboard"
          >
            {copied ? (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <rect x="8" y="8" width="12" height="12" rx="2" ry="2" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2" />
              </svg>
            )}
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-8 h-8 flex items-center justify-center bg-brutal-black text-white text-lg font-bold border-2 border-white hover:bg-white hover:text-brutal-black transition-colors uppercase"
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? '−' : '+'}
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className={`bg-neutral-50 transition-all duration-300 ease-in-out overflow-y-auto scrollbar-thin ${expanded ? 'max-h-[800px] opacity-100' : 'max-h-0 opacity-0'}`}>
        <div className="w-full p-3">
          <pre className="text-xs text-brutal-black leading-relaxed font-mono whitespace-pre-wrap break-all">
            {content}
          </pre>
        </div>
      </div>

      {/* Footer/Status Bar */}
      <div className="px-2 py-1 bg-neutral-200 border-t-2 border-brutal-black text-[10px] text-neutral-500 flex justify-between items-center">
        <span>{content.length} chars</span>
        <span>UTF-8</span>
      </div>
    </div>
  );
};
