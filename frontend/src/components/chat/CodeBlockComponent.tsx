import React, { useMemo, useState } from 'react';
import DOMPurify from 'dompurify';
import { useStatusStore } from '../../hooks/useStatusStore';
import { useI18n } from '../../i18n';
import { MermaidDiagram } from '../MermaidDiagram';

interface CodeBlockComponentProps {
  lang?: string;
  content: string;
  isStreaming?: boolean;
}

export const CodeBlockComponent: React.FC<CodeBlockComponentProps> = ({ lang, content, isStreaming }) => {
  const [expanded, setExpanded] = useState(true);
  const { setStatus } = useStatusStore();
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const lineCount = content.split('\n').length;

  const normalizedLang = (lang || '').toLowerCase();
  const isHtml = normalizedLang === 'html';
  const isMermaid = normalizedLang === 'mermaid';
  const isRenderable = isHtml || isMermaid;
  // Only switch to the rendered preview once streaming has finished, so we don't
  // sanitize/inject half-written markup or parse incomplete diagrams on every token.
  const [showPreview, setShowPreview] = useState(true);
  const renderPreview = isRenderable && showPreview && !isStreaming;
  const sanitizedHtml = useMemo(
    () => (renderPreview && isHtml ? DOMPurify.sanitize(content) : ''),
    [renderPreview, isHtml, content],
  );

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(content);
    setStatus(t('status.codeCopiedToClipboard'), 'success');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const safeLang = (lang || 'text').replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();

  return (
    <div className="my-3 font-mono text-sm border-2 border-brutal-black dark:border-zinc-500 bg-white dark:bg-zinc-900 group/code relative overflow-hidden">
      {/* Header Bar */}
      <div className="flex items-center justify-between gap-3 px-3 py-1.5 bg-brutal-black dark:bg-zinc-800 border-b-2 border-brutal-black dark:border-zinc-500 select-none overflow-hidden">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="text-white dark:text-brutal-yellow font-black uppercase text-[10px] truncate">
            {lang || t('codeBlock.code')}
          </span>
          <span className="text-white/55 dark:text-neutral-400 text-[10px] font-bold shrink-0">
            {t('codeBlock.lines', { count: lineCount })}
          </span>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover/code:opacity-100 focus-within:opacity-100 transition-opacity">
          {isRenderable && !isStreaming && (
            <button
              onClick={(e) => { e.stopPropagation(); setShowPreview(v => !v); }}
              className="h-6 px-1.5 flex items-center justify-center text-white dark:text-neutral-200 text-[10px] font-black uppercase border border-transparent hover:border-white dark:hover:border-zinc-400 hover:bg-white hover:text-brutal-black dark:hover:bg-zinc-700 transition-colors"
              title={showPreview ? t('codeBlock.viewSource') : t('codeBlock.viewPreview')}
            >
              {showPreview ? t('codeBlock.source') : t('codeBlock.preview')}
            </button>
          )}
          <button
            onClick={handleCopy}
            className="w-6 h-6 flex items-center justify-center text-white dark:text-neutral-200 border border-transparent hover:border-white dark:hover:border-zinc-400 hover:bg-white hover:text-brutal-black dark:hover:bg-zinc-700 transition-colors"
            title={t('codeBlock.copyCode')}
          >
            {copied ? (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <rect x="8" y="8" width="12" height="12" rx="2" ry="2" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2" />
              </svg>
            )}
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-6 h-6 flex items-center justify-center text-white dark:text-neutral-200 text-sm font-black border border-transparent hover:border-white dark:hover:border-zinc-400 hover:bg-white hover:text-brutal-black dark:hover:bg-zinc-700 transition-colors uppercase"
            title={expanded ? t('codeBlock.collapse') : t('codeBlock.expand')}
          >
            {expanded ? '−' : '+'}
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className={`bg-white dark:bg-zinc-950 overflow-hidden ${expanded ? 'block' : 'hidden'}`}>
        {renderPreview && isMermaid ? (
          <div className="px-3 py-2.5">
            <MermaidDiagram code={content} />
          </div>
        ) : renderPreview && isHtml ? (
          <div
            className="max-w-full px-3 py-2.5 overflow-x-auto bg-white text-brutal-black"
            dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
          />
        ) : (
          <pre className={`max-w-full text-[12px] text-brutal-black dark:text-neutral-100 px-3 py-2.5 leading-5 overflow-x-auto !bg-transparent whitespace-pre font-mono m-0`}>
            <code className={`language-${safeLang}`}>
              {content}
              {isStreaming && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>}
            </code>
          </pre>
        )}
      </div>
    </div>
  );
};
