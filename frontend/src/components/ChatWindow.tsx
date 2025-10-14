import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { streamChat } from '../lib/streaming';
import type { Message } from '../types/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import rehypePrism from 'rehype-prism-plus';
import { usePlan } from '../hooks/usePlan';

// Helper to normalize Python code indentation
function normalizePythonCode(code: string): string {
  const lines = code.split('\n');
  if (lines.length === 0) return code;
  
  // Find minimum indentation (ignoring empty lines)
  let minIndent = Infinity;
  for (const line of lines) {
    if (line.trim().length > 0) {
      const leadingSpaces = line.match(/^[ ]*/)?.[0].length || 0;
      minIndent = Math.min(minIndent, leadingSpaces);
    }
  }
  
  // Remove the minimum indentation from all lines
  if (minIndent > 0 && minIndent !== Infinity) {
    return lines.map(line => 
      line.trim().length > 0 ? line.slice(minIndent) : line
    ).join('\n');
  }
  
  return code;
}

// Helper to split assistant content into markdown + code blocks, tolerant of an open (unclosed) fence while streaming
function splitAssistantContent(content: string): { type: 'markdown' | 'code'; content: string; lang?: string }[] {
  const blocks: { type: 'markdown' | 'code'; content: string; lang?: string }[] = [];
  let i = 0;
  const len = content.length;
  let currentMarkdown = '';
  while (i < len) {
    const fenceStart = content.indexOf('```', i);
    if (fenceStart === -1) {
      currentMarkdown += content.slice(i);
      break;
    }
    currentMarkdown += content.slice(i, fenceStart);
    const langLineEnd = content.indexOf('\n', fenceStart + 3);
    if (langLineEnd === -1) {
      currentMarkdown += content.slice(fenceStart);
      i = len;
      break;
    }
    const langToken = content.slice(fenceStart + 3, langLineEnd).trim();
    // Clean and validate the language token - only allow valid language identifiers
    const cleanLang = langToken.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    const validLanguages = ['python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'sql', 'html', 'css', 'json', 'yaml', 'xml', 'bash', 'shell', 'powershell', 'php', 'ruby', 'swift', 'kotlin', 'dart', 'r', 'matlab', 'scala', 'perl', 'lua', 'haskell', 'clojure', 'elixir', 'erlang', 'fsharp', 'ocaml', 'pascal', 'fortran', 'cobol', 'assembly', 'asm', 'text', 'plain'];
    const lang = validLanguages.includes(cleanLang) ? cleanLang : 'text';
    const closingFence = content.indexOf('\n```', langLineEnd + 1);
    if (closingFence === -1) {
      if (currentMarkdown) {
        blocks.push({ type: 'markdown', content: currentMarkdown });
        currentMarkdown = '';
      }
      let codeBody = content.slice(langLineEnd + 1);
      // Normalize Python code indentation
      if (lang === 'python') {
        codeBody = normalizePythonCode(codeBody);
      }
      // If codeBody contains <details> or a line starting with **Step:, split them out as markdown
      const detailsIdx = codeBody.indexOf('<details>');
      const stepIdx = codeBody.search(/\n\*\*Step:/);
      let splitIdx = -1;
      if (detailsIdx !== -1) splitIdx = detailsIdx;
      if (stepIdx !== -1 && (splitIdx === -1 || stepIdx < splitIdx)) splitIdx = stepIdx;
      if (splitIdx !== -1) {
        blocks.push({ type: 'code', content: codeBody.slice(0, splitIdx), lang });
        codeBody = codeBody.slice(splitIdx);
        blocks.push({ type: 'markdown', content: codeBody });
      } else {
        blocks.push({ type: 'code', content: codeBody, lang });
      }
      i = len;
      break;
    } else {
      if (currentMarkdown) {
        blocks.push({ type: 'markdown', content: currentMarkdown });
        currentMarkdown = '';
      }
      let codeBody = content.slice(langLineEnd + 1, closingFence);
      // Normalize Python code indentation
      if (lang === 'python') {
        codeBody = normalizePythonCode(codeBody);
      }
      // If codeBody contains <details> or a line starting with **Step:, split them out as markdown
      const detailsIdx = codeBody.indexOf('<details>');
      const stepIdx = codeBody.search(/\n\*\*Step:/);
      let splitIdx = -1;
      if (detailsIdx !== -1) splitIdx = detailsIdx;
      if (stepIdx !== -1 && (splitIdx === -1 || stepIdx < splitIdx)) splitIdx = stepIdx;
      if (splitIdx !== -1) {
        blocks.push({ type: 'code', content: codeBody.slice(0, splitIdx), lang });
        codeBody = codeBody.slice(splitIdx);
        blocks.push({ type: 'markdown', content: codeBody });
      } else {
        blocks.push({ type: 'code', content: codeBody, lang });
      }
      i = closingFence + 4;
    }
  }
  if (currentMarkdown.trim() !== '') {
    blocks.push({ type: 'markdown', content: currentMarkdown });
  }
  return blocks.filter(b => b.content !== '');
}

const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(()=>setCopied(false),1500); }}
      className="absolute top-2 right-2 text-[10px] px-2 py-1 rounded bg-neutral-700/70 hover:bg-neutral-600 text-neutral-200"
      title="Copy code"
      type="button"
    >{copied ? 'Copied' : 'Copy'}</button>
  );
};

const MarkdownRenderer = (props: { content: string }) => {
  const RM: any = ReactMarkdown;
  // Only minimal normalization: collapse runs of 3+ newlines to 2, trim leading/trailing newlines.
  // whitespace-pre-wrap handles line breaks elegantly, so no need for further HTML tag/class stripping.
  const normalized = String(props.content)
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^\n+/, '')
    .replace(/\n+$/, '');

  return (
    // add `tight-lists` to increase selector specificity for our list overrides
    // remove whitespace-pre-wrap so stray newlines do not render as visible gaps
    <div className="prose tight-lists prose-sm max-w-none break-words">
      <RM
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, rehypePrism]}
        components={{
          code(codeProps: any) {
            const { inline, className, children, ...rest } = codeProps;
            // More robust language extraction with validation
            const match = /language-(\w+)/.exec(className || '');
            const lang = match ? match[1] : null;
            
            if (!inline && lang) {
              // Validate and clean the language name
              const cleanLang = lang.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
              const safeClassName = cleanLang ? `language-${cleanLang}` : 'language-text';
              
              return (
                <pre className="max-w-3xl overflow-x-auto text-xs bg-neutral-900 text-neutral-100 border border-neutral-800 rounded-lg p-3 font-mono leading-relaxed break-words">
                  <code className={safeClassName}>{String(children)}</code>
                </pre>
              );
            }
            return <code className="bg-neutral-100 px-1.5 py-0.5 rounded text-[11px] font-mono text-brand-600 break-words" {...rest}>{children}</code>;
          },
          a(aProps: any) { const { href, children } = aProps; return <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline break-words">{children}</a>; },
          table(p: any) { return <div className="overflow-x-auto"><table className="text-xs border border-neutral-200">{p.children}</table></div>; },
          th(p: any) { return <th className="border px-2 py-1 bg-neutral-50 font-semibold">{p.children}</th>; },
          td(p: any) { return <td className="border px-2 py-1 align-top">{p.children}</td>; },
          ul(p: any) { return <ul className="list-disc pl-5">{p.children}</ul>; },
          ol(p: any) { return <ol className="list-decimal pl-5">{p.children}</ol>; },
          h1(p: any) { return <h1 className="text-xl font-semibold mb-1 break-words">{p.children}</h1>; },
          h2(p: any) { return <h2 className="text-lg font-semibold mb-1 break-words">{p.children}</h2>; },
          h3(p: any) { return <h3 className="text-base font-semibold mb-1 break-words">{p.children}</h3>; },
          p(pArg: any) { return <p className="leading-relaxed break-words whitespace-pre-wrap m-0">{pArg.children}</p>; },
          blockquote(p: any) { return <blockquote className="border-l-4 border-brand-600/30 pl-3 italic text-neutral-600 break-words">{p.children}</blockquote>; }
        }}
      >
  {normalized}
      </RM>
    </div>
  );
};

export const ChatWindow: React.FC = () => {
  const { messages, addMessage, updateAssistantStreaming, config, backendConfig, newAssistantMessage, shouldResetNext, consumeResetFlag, forceSaveNow, setIsStreaming, currentChatId } = useChatStore();
  const { setPlan, refresh: refreshPlan } = usePlan();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(false);

  // Safeguard against undefined state
  const safeMessages = messages || [];
  const safeConfig = config || { model: '', agent: '', tools: [] };
  const safeBackendConfig = backendConfig || null;
  


  // Track whether automatic scrolling is allowed. If the user manually scrolls away
  // from the bottom, disable auto-scroll until they scroll back to the bottom.
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const autoScrollEnabledRef = useRef(true);

  // Helper to determine if the user is at (or very near) the bottom
  const isAtBottom = (el: Element | null) => {
    if (!el) return true;
    const tolerance = 24; // px from bottom to still consider "at bottom"
    return el.scrollHeight - el.scrollTop - el.clientHeight <= tolerance;
  };

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const onUserScroll = (e: Event) => {
      // When the user scrolls (wheel/scroll/touch), if they're not at the bottom,
      // disable auto-scrolling. If they reach the bottom again, re-enable it.
      const atBottom = isAtBottom(el);
      autoScrollEnabledRef.current = atBottom;
    };

    // Listen to a few events that indicate user interaction
    el.addEventListener('scroll', onUserScroll, { passive: true });
    el.addEventListener('wheel', onUserScroll, { passive: true });
    el.addEventListener('touchstart', onUserScroll, { passive: true });

    return () => {
      el.removeEventListener('scroll', onUserScroll);
      el.removeEventListener('wheel', onUserScroll);
      el.removeEventListener('touchstart', onUserScroll);
    };
  }, []);

  // Auto-scroll when messages change, but only if autoScrollEnabledRef is true
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (autoScrollEnabledRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else {
      // If auto-scroll is disabled, do nothing. However, if the user has scrolled
      // back to the bottom (maybe by clicking a "Jump to bottom" UI later),
      // the scroll listener will re-enable auto-scroll.
      // Optionally, we could show a subtle indicator here in future.
    }
  }, [safeMessages]);

  const configReady = safeBackendConfig && safeConfig.model && safeConfig.agent;

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || loading || !configReady) return;
    const resetFlag = shouldResetNext;
    if (resetFlag) consumeResetFlag();
    setInput('');
    addMessage({ role: 'user', content: prompt });
    setLoading(true);
    setIsStreaming(true);
    try {
      await streamChat(prompt, safeConfig, {
        onDelta: (partial: string) => { updateAssistantStreaming(partial); },
        onAction: () => { /* compatibility */ },
        onNewAssistantMessage: () => { newAssistantMessage(); },
        onPlanUpdate: (p: any) => { 
          // Refresh plan from database instead of using the streamed data
          refreshPlan(currentChatId); 
        },
        onStreamComplete: () => { 
          setIsStreaming(false);
          // Add a delay to ensure all message updates have processed
          setTimeout(async () => {
            try {
              await forceSaveNow();
            } catch (error) {
              console.error('Error in forceSaveNow from onStreamComplete:', error);
            }
          }, 200);
        }
      }, safeBackendConfig?.codeTag || '<code>', resetFlag, currentChatId);
      
    } catch (error) {
      console.error('Error during streaming:', error);
    } finally { 
      setLoading(false); 
      setIsStreaming(false);
      // Ensure we save even if onStreamComplete wasn't called
      setTimeout(async () => {
        try {
          await forceSaveNow();
        } catch (error) {
          console.error('Error in forceSaveNow from finally block:', error);
        }
      }, 600);
    }
  };

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden bg-white">
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-6 pb-24 space-y-6 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-neutral-300/80">
        {safeMessages.map((m: Message, idx: number) => {
          const isUser = m.role === 'user';
          const blocks = isUser ? [{ type: 'markdown', content: m.content } as { type: 'markdown'; content: string; lang?: string }] : splitAssistantContent(m.content);
          let rawMetaLine: string | null = null;
          if (!isUser) {
            const firstMarkdown = blocks.find(b => b.type === 'markdown');
            if (firstMarkdown) {
              const lines = firstMarkdown.content.split(/\n/);
              const metaIdx = lines.findIndex(l => l.trim().startsWith('**Step:'));
              if (metaIdx !== -1) {
                rawMetaLine = lines[metaIdx];
                lines.splice(metaIdx, 1);
                firstMarkdown.content = lines.join('\n');
              }
            }
          }
          const displayMeta = rawMetaLine ? rawMetaLine.replace(/\*\*/g, '') : null;
          const alignClass = isUser ? 'justify-end' : 'justify-start';
          return (
            <div key={idx} className="w-full flex flex-col">
              {!isUser && displayMeta && (
                <div className={`flex ${alignClass} w-full mb-0.5`}> 
                  <div className="text-[10px] font-medium tracking-wide text-neutral-500 px-1">{displayMeta}</div>
                </div>
              )}
              <div className={`flex ${alignClass} w-full`}>
                <div className={`group w-full max-w-3xl break-words overflow-visible ${isUser ? 'bg-gradient-to-tr from-brand-600 to-brand-500 text-white' : 'bg-white/90 border border-neutral-200 text-neutral-800'} rounded-xl shadow-sm px-5 py-3 space-y-3 text-sm leading-relaxed relative`}>
                  {isUser ? (
                    <div className="prose prose-sm prose-invert max-w-none text-white break-words">{m.content}</div>
                  ) : (
                    blocks.map((b, bi) => b.type === 'markdown' ? (
                      <MarkdownRenderer key={bi} content={b.content} />
                    ) : (
                      <div key={bi} className="relative">
                        <CopyButton text={b.content} />
                        <pre className="max-w-3xl overflow-x-auto text-xs bg-neutral-50 border border-neutral-200 rounded-lg p-3 font-mono leading-relaxed">
                          <code className={`language-${((b as any).lang || 'text').replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase() || 'text'}`}>{b.content}</code>
                        </pre>
                      </div>
                    ))
                  )}
                  {/* end user/assistant content */}
                  {!isUser && idx === safeMessages.length - 1 && loading && (
                    <div className="flex gap-1 items-center text-[10px] text-neutral-400 animate-pulse">Thinking<span className="w-1 h-1 bg-neutral-300 rounded-full animate-bounce [animation-delay:-0.2s]"></span><span className="w-1 h-1 bg-neutral-300 rounded-full animate-bounce [animation-delay:-0.05s]"></span><span className="w-1 h-1 bg-neutral-300 rounded-full animate-bounce"></span></div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {!configReady && (
          <div className="text-xs text-neutral-400">Loading backend configuration...</div>
        )}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="border-t border-neutral-200 p-4 flex gap-3 bg-white/95">
        <div className="flex-1 relative">
          <textarea
            className="flex-1 w-full resize-none rounded-xl bg-neutral-50 border border-neutral-300 focus:border-brand-500 focus:ring-1 focus:ring-brand-500/40 focus:outline-none px-4 py-3 text-sm placeholder-neutral-400 shadow-inner"
            rows={3}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!loading && configReady && input.trim()) {
                  send();
                }
              }
            }}
            placeholder={configReady ? 'Ask me anything...' : 'Waiting for config...'}
            disabled={!configReady}
          />
          <div className="absolute bottom-2 right-3 text-[10px] text-neutral-400 select-none">Enter to send • Shift+Enter newline</div>
        </div>
        <button
            type="submit"
            className="h-12 self-end rounded-lg bg-brand-600 hover:bg-brand-500 active:bg-brand-500/90 transition-colors px-5 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed shadow text-white"
            disabled={loading || !configReady}
          >
            {loading ? 'Sending…' : 'Send'}
          </button>
      </form>
    </div>
  );
};
