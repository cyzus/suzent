import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore.js';
import { streamChat } from '../lib/streaming.js';
import type { Message } from '../types/api.js';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import rehypePrism from 'rehype-prism-plus';
import { usePlan } from '../hooks/usePlan';
import Prism from 'prismjs';

// Helper to split assistant content into markdown + code blocks, tolerant of an open (unclosed) fence while streaming
function splitAssistantContent(content: string): { type: 'markdown' | 'code'; content: string; lang?: string }[] {
  const blocks: { type: 'markdown' | 'code'; content: string; lang?: string }[] = [];
  let i = 0;
  const len = content.length;
  let currentMarkdown = '';
  while (i < len) {
    const fenceStart = content.indexOf('```', i);
    if (fenceStart === -1) { // no more fences
      currentMarkdown += content.slice(i);
      break;
    }
    // append markdown before fence
    currentMarkdown += content.slice(i, fenceStart);
    // detect language
    const langLineEnd = content.indexOf('\n', fenceStart + 3);
    if (langLineEnd === -1) { // fence not complete yet
      currentMarkdown += content.slice(fenceStart); // treat as plain until newline arrives
      i = len;
      break;
    }
    const langToken = content.slice(fenceStart + 3, langLineEnd).trim();
    const lang = langToken || 'text';
    // look for closing fence
    const closingFence = content.indexOf('\n```', langLineEnd + 1);
    if (closingFence === -1) {
      // Open code fence without closure yet -> push accumulated markdown, then code block with current partial code
      if (currentMarkdown) {
        blocks.push({ type: 'markdown', content: currentMarkdown });
        currentMarkdown = '';
      }
      const codeBody = content.slice(langLineEnd + 1); // everything after lang line
      blocks.push({ type: 'code', content: codeBody, lang });
      i = len; // done
      break;
    } else {
      // Closed block
      if (currentMarkdown) {
        blocks.push({ type: 'markdown', content: currentMarkdown });
        currentMarkdown = '';
      }
      const codeBody = content.slice(langLineEnd + 1, closingFence);
      blocks.push({ type: 'code', content: codeBody, lang });
      i = closingFence + 4; // skip over \n```
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
  return (
    <RM
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize, rehypePrism]}
      components={{
        code(codeProps: any) {
          const { inline, className, children, ...rest } = codeProps;
            const match = /language-(\w+)/.exec(className || '');
            if (!inline && match) {
              return (
                <pre className="max-w-3xl overflow-x-auto text-xs bg-neutral-900 text-neutral-100 border border-neutral-800 rounded-lg p-3 font-mono leading-relaxed">
                  <code className={className}>{String(children)}</code>
                </pre>
              );
            }
            return <code className="bg-neutral-100 px-1.5 py-0.5 rounded text-[11px] font-mono text-brand-600" {...rest}>{children}</code>;
        },
        a(aProps: any) { const { href, children } = aProps; return <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline">{children}</a>; },
        table(p: any) { return <div className="overflow-x-auto"><table className="text-xs border border-neutral-200">{p.children}</table></div>; },
        th(p: any) { return <th className="border px-2 py-1 bg-neutral-50 font-semibold">{p.children}</th>; },
        td(p: any) { return <td className="border px-2 py-1 align-top">{p.children}</td>; },
        ul(p: any) { return <ul className="list-disc ml-5 space-y-1">{p.children}</ul>; },
        ol(p: any) { return <ol className="list-decimal ml-5 space-y-1">{p.children}</ol>; },
        h1(p: any) { return <h1 className="text-xl font-semibold mt-4 mb-2">{p.children}</h1>; },
        h2(p: any) { return <h2 className="text-lg font-semibold mt-4 mb-2">{p.children}</h2>; },
        h3(p: any) { return <h3 className="text-base font-semibold mt-4 mb-2">{p.children}</h3>; },
        p(pArg: any) { return <p className="leading-relaxed">{pArg.children}</p>; },
        blockquote(p: any) { return <blockquote className="border-l-4 border-brand-600/30 pl-3 italic text-neutral-600">{p.children}</blockquote>; }
      }}
      className="prose prose-sm max-w-none"
    >
      {props.content}
    </RM>
  );
};

export const ChatWindow: React.FC = () => {
  const { messages, addMessage, updateAssistantStreaming, config, backendConfig, newAssistantMessage } = useChatStore();
  const { setPlan } = usePlan();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => { Prism.highlightAll(); }, [messages]);

  const configReady = backendConfig && config.model && config.agent;

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || loading || !configReady) return;
    setInput('');
    addMessage({ role: 'user', content: prompt });
    setLoading(true);
    try {
      await streamChat(prompt, config, {
        onDelta: (partial: string) => { updateAssistantStreaming(partial); Prism.highlightAll(); },
        onAction: () => { /* compatibility */ },
        onNewAssistantMessage: () => { newAssistantMessage(); },
        onPlanUpdate: (p: any) => { setPlan(p); }
      }, backendConfig?.codeTag || '<code>');
    } finally { setLoading(false); }
  };

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden bg-white">
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-neutral-300/80">
        {messages.map((m: Message, idx: number) => {
          const isUser = m.role === 'user';
          const blocks = isUser ? [{ type: 'markdown', content: m.content } as { type: 'markdown'; content: string; lang?: string }] : splitAssistantContent(m.content);
          return (
            <div key={idx} className={`flex ${isUser ? 'justify-end' : 'justify-start'} w-full`}>
              <div className={`group max-w-3xl w-fit ${isUser ? 'bg-gradient-to-tr from-brand-600 to-brand-500 text-white' : 'bg-white/90 border border-neutral-200 text-neutral-800'} rounded-xl shadow-sm px-5 py-3 space-y-3 text-sm leading-relaxed relative`}>                
                {blocks.map((b, bi) => b.type === 'markdown' ? (
                  <MarkdownRenderer key={bi} content={b.content} />
                ) : (
                  <div key={bi} className="relative">
                    <CopyButton text={b.content} />
                    <pre className="max-w-3xl overflow-x-auto text-xs bg-neutral-50 border border-neutral-200 rounded-lg p-3 font-mono leading-relaxed">
                      <code className={`language-${(b as any).lang || 'text'}`}>{b.content}</code>
                    </pre>
                  </div>
                ))}
                {!isUser && idx === messages.length - 1 && loading && (
                  <div className="flex gap-1 items-center text-[10px] text-neutral-400 animate-pulse">Thinking<span className="w-1 h-1 bg-neutral-300 rounded-full animate-bounce [animation-delay:-0.2s]"></span><span className="w-1 h-1 bg-neutral-300 rounded-full animate-bounce [animation-delay:-0.05s]"></span><span className="w-1 h-1 bg-neutral-300 rounded-full animate-bounce"></span></div>
                )}
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
