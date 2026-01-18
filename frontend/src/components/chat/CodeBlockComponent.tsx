import React, { useState } from 'react';
import { useStatusStore } from '../../hooks/useStatusStore';

interface CodeBlockComponentProps {
  lang?: string;
  content: string;
  isStreaming?: boolean;
}

export const CodeBlockComponent: React.FC<CodeBlockComponentProps> = ({ lang, content, isStreaming }) => {
  const [expanded, setExpanded] = useState(true);
  const { setStatus } = useStatusStore();
  const [copied, setCopied] = useState(false);
  const lineCount = content.split('\n').length;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(content);
    setStatus('CODE_COPIED_TO_CLIPBOARD', 'success');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const safeLang = (lang || 'text').replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();

  if (safeLang === 'text') {
    return (
      <div className="my-2 group/code relative border-2 border-brutal-black bg-neutral-50 shadow-brutal-sm p-4">
        <div className="absolute top-2 right-2 opacity-0 group-hover/code:opacity-100 transition-opacity z-10">
          <button
            onClick={handleCopy}
            className="w-8 h-8 flex items-center justify-center bg-white text-brutal-black border-2 border-brutal-black hover:bg-brutal-yellow transition-colors shadow-sm"
            title="Copy text"
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
        </div>
        <div className="bg-transparent overflow-hidden">
          <pre className="max-w-full text-xs text-brutal-code-text p-0 font-sans leading-relaxed overflow-x-auto whitespace-pre-wrap break-all !bg-transparent">
            <code className={`language-${safeLang}`}>
              {content}
              {isStreaming && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>}
            </code>
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div className="my-4 font-mono text-sm border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] bg-white group/code relative">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-brutal-black border-b-3 border-brutal-black select-none overflow-hidden">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="flex items-center justify-center w-6 h-6 bg-white border-2 border-white text-brutal-black font-bold text-xs shrink-0">
            <span>{'{}'}</span>
          </div>
          <span className="text-white font-bold uppercase tracking-wider text-xs truncate">
            {lang || 'CODE'}
          </span>
          <span className="text-neutral-400 text-[10px] font-bold shrink-0">
            {lineCount} LINES
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="w-8 h-8 flex items-center justify-center bg-brutal-black text-white border-2 border-white hover:bg-white hover:text-brutal-black transition-colors"
            title="Copy code"
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
      <div className={`bg-brutal-code-bg transition-all duration-300 ease-in-out overflow-hidden ${expanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'}`}>
        <pre className={`max-w-full text-xs text-brutal-code-text p-4 pt-4 leading-relaxed overflow-x-auto !bg-transparent whitespace-pre font-mono`}>
          <code className={`language-${safeLang}`}>
            {content}
            {isStreaming && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>}
          </code>
        </pre>
      </div>
    </div>
  );
};
