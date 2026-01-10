import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { streamChat } from '../lib/streaming';
import type { Message } from '../types/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import rehypePrism from 'rehype-prism-plus';
import { usePlan } from '../hooks/usePlan';
import { useMemory } from '../hooks/useMemory';
import { generateBlockKey, splitAssistantContent } from '../lib/chatUtils';
import { useStatusStore } from '../hooks/useStatusStore';
import { PlanProgress } from './PlanProgress';
import { NewChatView } from './NewChatView';
import { ChatInputPanel } from './ChatInputPanel';
import { useTypewriter } from '../hooks/useTypewriter';



const LogBlock: React.FC<{ title?: string; content: string }> = ({ title, content }) => {
  // Auto-expand if content is short (less than 5 lines or 300 chars)
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
      <div className="flex items-center justify-between px-3 py-2 bg-brutal-black border-b-3 border-brutal-black select-none">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-6 h-6 bg-white border-2 border-white text-brutal-black font-bold text-xs">
            <span>{'>_'}</span>
          </div>
          <span className="text-white font-bold uppercase tracking-wider text-xs truncate max-w-[200px]">
            {title || 'System Log'}
          </span>
          <span className="text-neutral-400 text-[10px] font-bold">
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

      {/* Footer/Status Bar (Optional, adds to the window feel) */}
      <div className="px-2 py-1 bg-neutral-200 border-t-2 border-brutal-black text-[10px] text-neutral-500 flex justify-between items-center">
        <span>{content.length} chars</span>
        <span>UTF-8</span>
      </div>
    </div>
  );
};

const CopyButton: React.FC<{ text: string; className?: string; color?: string }> = ({ text, className, color = 'bg-brutal-green' }) => {
  const { setStatus } = useStatusStore();
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setStatus('COPIED_TO_CLIPBOARD', 'success');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className={`w-8 h-8 flex items-center justify-center ${color} border-2 border-brutal-black shadow-brutal-sm hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-none transition-all duration-100 text-brutal-black ${className || 'absolute top-2 right-2'}`}
      title="Copy to clipboard"
      type="button"
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
  );
};

const CodeBlockComponent: React.FC<{ lang?: string; content: string; isStreaming?: boolean }> = ({ lang, content, isStreaming }) => {
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
            <code className={`language-${safeLang}`}>{content}{isStreaming && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>}</code>
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div className="my-4 font-mono text-sm border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] bg-white group/code relative">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-brutal-black border-b-3 border-brutal-black select-none">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-6 h-6 bg-white border-2 border-white text-brutal-black font-bold text-xs">
            <span>{'{}'}</span>
          </div>
          <span className="text-white font-bold uppercase tracking-wider text-xs truncate max-w-[200px]">
            {lang || 'CODE'}
          </span>
          <span className="text-neutral-400 text-[10px] font-bold">
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
        <pre className={`max-w-full text-xs text-brutal-code-text p-4 pt-4 leading-relaxed overflow-x-auto !bg-transparent ${safeLang === 'text' ? 'whitespace-pre-wrap break-all font-sans' : 'whitespace-pre font-mono'}`}>
          <code className={`language-${safeLang}`}>{content}{isStreaming && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>}</code>
        </pre>
      </div>
    </div>
  );
};

const MarkdownRenderer = React.memo((props: { content: string }) => {
  const RM: any = ReactMarkdown;
  // Only minimal normalization: collapse runs of 3+ newlines to 2, trim leading/trailing newlines.
  // whitespace-pre-wrap handles line breaks elegantly, so no need for further HTML tag/class stripping.
  const normalized = String(props.content)
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^\n+/, '')
    .replace(/\n+$/, '');

  // Sanitize fenced code block info strings so rehype-prism-plus never
  // receives an invalid language token which causes it to throw (for
  // example incoming fences like ```<body> or malformed tokens). We only
  // allow a known whitelist of language identifiers; otherwise we remove
  // the info string so the highlighter treats the block as plain text.
  const allowedLanguages = new Set([
    'python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'go', 'rust', 'sql', 'html', 'css', 'json', 'yaml', 'xml', 'bash', 'shell', 'powershell', 'php', 'ruby', 'swift', 'kotlin', 'dart', 'r', 'matlab', 'scala', 'perl', 'lua', 'haskell', 'clojure', 'elixir', 'erlang', 'fsharp', 'ocaml', 'pascal', 'fortran', 'cobol', 'assembly', 'asm', 'text', 'plain'
  ]);

  const sanitized = normalized.replace(/```\s*([^\n`]*)/g, (_m, info) => {
    // Take only the first token on the fence line (the language identifier)
    const token = String(info || '').trim().split(/\s+/)[0] || '';
    const clean = token.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    // If the cleaned token is not in our allowed set, drop the info
    // string so rehype-prism-plus does not receive an unknown language.
    return allowedLanguages.has(clean) ? `\`\`\`${clean}` : '```';
  });

  return (
    // add `tight-lists` to increase selector specificity for our list overrides
    // remove whitespace-pre-wrap so stray newlines do not render as visible gaps
    <div className="prose tight-lists prose-sm max-w-none break-words select-text">
      <RM
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          rehypeRaw,
          [rehypeSanitize, {
            ...defaultSchema,
            tagNames: [...(defaultSchema.tagNames || []), 'details', 'summary'],
            attributes: {
              ...defaultSchema.attributes,
              details: ['open'],
              summary: [],
              code: ['className'],
              span: ['className']
            }
          }],
          rehypePrism
        ]}
        components={{
          details(p: any) {
            return (
              <details className="group border-3 border-brutal-black bg-white my-6 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] open:shadow-none open:translate-x-[2px] open:translate-y-[2px] transition-all overflow-hidden">
                {p.children}
              </details>
            );
          },
          summary(p: any) {
            return (
              <summary className="cursor-pointer font-mono font-bold p-3 bg-brutal-black text-white border-b-3 border-brutal-black group-open:border-b-3 list-none flex items-center justify-between select-none hover:bg-neutral-800 transition-colors uppercase tracking-wider text-xs">
                <div className="flex items-center gap-3">
                  <span className="text-white transform group-open:rotate-90 transition-transform inline-block">►</span>
                  <span>{p.children}</span>
                </div>
                <span className="text-[10px] text-neutral-400 group-open:hidden">CLICK TO EXPAND</span>
                <span className="text-[10px] text-neutral-400 hidden group-open:inline">SYSTEM_LOG_ACTIVE</span>
              </summary>
            );
          },
          pre(p: any) {
            // Check if this pre contains a code block (which is handled by the code component)
            // We check the HAST node to see if it's a pre > code structure
            if (p.node && p.node.children && p.node.children.length === 1 && p.node.children[0].tagName === 'code') {
              return <>{p.children}</>;
            }

            // Special handling for pre tags inside details (logs)
            return (
              <div className="bg-neutral-50 p-4 overflow-x-auto">
                <pre className="font-mono text-xs text-brutal-black leading-relaxed whitespace-pre-wrap break-all">
                  {p.children}
                </pre>
              </div>
            );
          },
          code(codeProps: any) {
            const { inline, className, children, ...rest } = codeProps;
            // More robust language extraction with validation
            const match = /language-([a-zA-Z0-9_-]+)/.exec(className || '');
            const lang = match ? match[1] : null;
            const content = String(children).replace(/\n$/, '');

            // Heuristic: Demote short, single-line "text" blocks to inline styling
            // This prevents "Thought: [BLOCK] variable [BLOCK]" visual stutter
            const isText = !lang || lang === 'text';
            const isSingleLine = !content.includes('\n');
            const isShort = content.length < 60;

            if (!inline && !(isText && isSingleLine && isShort)) {
              return <CodeBlockComponent lang={lang || 'text'} content={content} />;
            }
            return <code className="bg-brutal-yellow px-1.5 py-0.5 border-2 border-brutal-black text-[11px] font-mono text-brutal-black font-bold break-words" {...rest}>{children}</code>;
          },
          a(aProps: any) { const { href, children } = aProps; return <a href={href} target="_blank" rel="noopener noreferrer" className="text-brutal-blue hover:bg-brutal-yellow font-bold underline break-words transition-colors duration-100">{children}</a>; },
          table(p: any) { return <div className="overflow-x-auto"><table className="text-xs border-3 border-brutal-black">{p.children}</table></div>; },
          th(p: any) { return <th className="border-2 border-brutal-black px-2 py-1 bg-brutal-yellow font-bold">{p.children}</th>; },
          td(p: any) { return <td className="border-2 border-brutal-black px-2 py-1 align-top">{p.children}</td>; },
          ul(p: any) { return <ul className="list-disc pl-5">{p.children}</ul>; },
          ol(p: any) { return <ol className="list-decimal pl-5">{p.children}</ol>; },
          h1(p: any) { return <h1 className="text-xl font-brutal font-bold mb-2 break-words uppercase">{p.children}</h1>; },
          h2(p: any) { return <h2 className="text-lg font-brutal font-bold mb-2 break-words uppercase">{p.children}</h2>; },
          h3(p: any) { return <h3 className="text-base font-bold mb-1 break-words uppercase">{p.children}</h3>; },
          p(pArg: any) {
            // Style step metadata lines differently
            const text = String(pArg.children?.[0] || '');
            if (text.startsWith('Step: ') && text.includes('tokens')) {
              return (
                <p className="flex items-center gap-3 text-xs sm:text-sm text-brutal-black border-4 border-brutal-black pt-4 pb-3 mt-6 font-mono font-black break-words whitespace-pre-wrap m-0 bg-brutal-yellow -mx-5 px-5 shadow-brutal-sm uppercase tracking-wider">
                  <span aria-hidden="true" className="text-lg leading-none">▣</span>
                  <span className="flex-1">{pArg.children}</span>
                </p>
              );
            }
            return <p className="leading-relaxed break-words whitespace-pre-wrap m-0">{pArg.children}</p>;
          },
          blockquote(p: any) { return <blockquote className="border-l-4 border-brutal-black pl-3 italic text-neutral-600 break-words bg-neutral-50 py-1 pr-2">{p.children}</blockquote>; }
        }}
      >
        {sanitized}
      </RM>
    </div>
  );
});

// Component to handle typewriter effect for the active streaming message
const StreamingMessageContent: React.FC<{
  content: string;
  isStreaming: boolean;
  onBlockRender: (blocks: any[]) => React.ReactNode;
}> = ({ content, isStreaming, onBlockRender }) => {
  // Use typewriter effect only if streaming
  const displayedContent = useTypewriter(content, 10, isStreaming);

  // Split content based on what's currently displayed
  const blocks = splitAssistantContent(displayedContent);

  return <>{onBlockRender(blocks)}</>;
};

export const ChatWindow: React.FC = () => {
  const {
    messages,
    addMessage,
    updateLastUserMessageImages,
    updateAssistantStreaming,
    config,
    backendConfig,
    newAssistantMessage,
    setConfig,
    setStepInfo,
    shouldResetNext,
    consumeResetFlag,
    forceSaveNow,
    setIsStreaming,
    currentChatId,
    createNewChat,
    removeEmptyAssistantMessage,
    isStreaming,
    activeStreamingChatId,
  } = useChatStore();
  const { refresh: refreshPlan, applySnapshot: applyPlanSnapshot, plan } = usePlan();
  const { loadCoreMemory, loadStats } = useMemory();
  const [input, setInput] = useState('');
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
  const [isPlanDocked, setIsPlanDocked] = useState(false);
  const [isPlanExpanded, setIsPlanExpanded] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const stopInFlightRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const streamingForCurrentChat = isStreaming && activeStreamingChatId === currentChatId;

  // Safeguard against undefined state
  const safeMessages = messages || [];
  const safeConfig = config || { model: '', agent: '', tools: [] };
  const safeBackendConfig = backendConfig || null;



  // Track whether automatic scrolling is allowed. If the user manually scrolls away
  // from the bottom, disable auto-scroll until they scroll back to the bottom.
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const autoScrollEnabledRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Helper to determine if the user is at (or very near) the bottom
  const isAtBottom = (el: Element | null) => {
    if (!el) return true;
    const tolerance = 50; // px from bottom to still consider "at bottom"
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
      setShowScrollButton(!atBottom);
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
    }
  }, [safeMessages, isStreaming]);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    autoScrollEnabledRef.current = true;
    setShowScrollButton(false);
  };

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  const configReady = !!(safeBackendConfig && safeConfig.model && safeConfig.agent);

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    setSelectedImages(prev => [...prev, ...imageFiles]);
    if (fileInputRef.current) {
      fileInputRef.current.value = ''; // Reset input to allow re-selecting same file
    }
  };

  const removeImage = (index: number) => {
    setSelectedImages(prev => prev.filter((_, i) => i !== index));
  };

  // Drag and drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set dragging to false if leaving the chat window entirely
    if (e.currentTarget === e.target) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    if (imageFiles.length > 0) {
      setSelectedImages(prev => [...prev, ...imageFiles]);
    }
  };

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming || !configReady) return;

    const resetFlag = shouldResetNext;
    if (resetFlag) consumeResetFlag();
    setInput('');

    // Capture images and clear selection
    const imagesToSend = [...selectedImages];
    setSelectedImages([]);

    // Create the chat first if needed
    let chatIdForSend = currentChatId;
    if (!chatIdForSend) {
      chatIdForSend = await createNewChat();
      if (!chatIdForSend) {
        console.error('Unable to initialize chat before sending message.');
        return;
      }
    }

    // Convert File objects to data URLs for immediate display
    const imagePreviewPromises = imagesToSend.map(file => {
      return new Promise<{ id: string; data: string; mime_type: string; filename: string }>((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const dataUrl = e.target?.result as string;
          // Extract base64 part from data URL (remove "data:image/jpeg;base64," prefix)
          const base64Data = dataUrl.split(',')[1];
          resolve({
            id: crypto.randomUUID(),
            data: base64Data,
            mime_type: file.type,
            filename: file.name
          });
        };
        reader.readAsDataURL(file);
      });
    });

    // Wait for all images to be converted to data URLs
    const imagePreviews = imagesToSend.length > 0 ? await Promise.all(imagePreviewPromises) : undefined;

    // Add user message with client-side image previews
    addMessage({ role: 'user', content: prompt, images: imagePreviews }, chatIdForSend);

    setIsStreaming(true, chatIdForSend);
    stopInFlightRef.current = false;
    try {
      await streamChat(
        prompt,
        safeConfig,
        {
          onDelta: (partial: string) => { updateAssistantStreaming(partial, chatIdForSend); },
          onAction: () => { /* compatibility */ },
          onNewAssistantMessage: () => { newAssistantMessage(chatIdForSend); },
          onStepComplete: (stepInfo: string) => { setStepInfo(stepInfo, chatIdForSend); },
          onImagesProcessed: (processedImages: any[]) => {
            // Replace client-side previews with backend-compressed versions
            // This ensures the stored versions match what the agent received
            updateLastUserMessageImages(processedImages, chatIdForSend);
          },
          onPlanUpdate: (snapshot: any) => {
            applyPlanSnapshot(snapshot);
            refreshPlan(chatIdForSend);
          },
          onStreamComplete: () => {
            setIsStreaming(false, chatIdForSend);
            // Add a delay to ensure all message updates have processed
            setTimeout(async () => {
              try {
                await forceSaveNow(chatIdForSend);
              } catch (error) {
                console.error('Error in forceSaveNow from onStreamComplete:', error);
              }
            }, 200);
            // Refresh memory views so core blocks reflect tool updates
            // Fetch user-level blocks (persona/user/facts) since those persist across chats
            try { loadCoreMemory(); loadStats(); } catch { }
          },
          onStreamStopped: () => {
            setIsStreaming(false, chatIdForSend);
            removeEmptyAssistantMessage(chatIdForSend);
            stopInFlightRef.current = false;
          },
        },
        safeBackendConfig?.codeTag || '<code>',
        resetFlag,
        chatIdForSend,
        imagesToSend.length > 0 ? imagesToSend : undefined
      );
    } catch (error) {
      console.error('Error during streaming:', error);
    } finally {
      setIsStreaming(false, chatIdForSend);
      // Ensure we save even if onStreamComplete wasn't called
      setTimeout(async () => {
        try {
          await forceSaveNow(chatIdForSend);
        } catch (error) {
          console.error('Error in forceSaveNow from finally block:', error);
        }
      }, 600);
      stopInFlightRef.current = false;
    }
  };

  const stopStreaming = async () => {
    if (!isStreaming || stopInFlightRef.current) return;
    stopInFlightRef.current = true;
    const targetChatId = activeStreamingChatId;
    if (!targetChatId) {
      stopInFlightRef.current = false;
      return;
    }
    try {
      const res = await fetch('/api/chat/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: targetChatId, reason: 'User requested stop' })
      });
      if (!res.ok) {
        console.error('Stop request failed:', res.status, res.statusText);
        stopInFlightRef.current = false;
      }
    } catch (error) {
      console.error('Error sending stop request:', error);
      stopInFlightRef.current = false;
    }
  };

  return (
    <div
      className="flex flex-row flex-1 h-full overflow-hidden bg-neutral-50 relative"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-brutal-blue/20 border-4 border-dashed border-brutal-black flex items-center justify-center pointer-events-none">
          <div className="bg-brutal-yellow border-4 border-brutal-black shadow-brutal-xl px-8 py-6 flex flex-col items-center gap-3">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-brutal-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="text-lg font-bold text-brutal-black uppercase">Drop Images Here</span>
          </div>
        </div>
      )}

      {/* Main Chat Column */}
      <div className="flex flex-col flex-1 min-w-0 h-full relative">


        <div className="relative flex-1 min-h-0">
          <div ref={scrollContainerRef} className="h-full overflow-y-auto p-4 md:p-6 pb-6 scrollbar-thin">
            {safeMessages.length === 0 ? (
              <NewChatView
                input={input}
                setInput={setInput}
                selectedImages={selectedImages}
                handleImageSelect={handleImageSelect}
                removeImage={removeImage}
                send={send}
                isStreaming={isStreaming}
                config={safeConfig}
                setConfig={setConfig}
                backendConfig={safeBackendConfig}
                fileInputRef={fileInputRef}
                textareaRef={textareaRef}
                configReady={configReady}
                streamingForCurrentChat={streamingForCurrentChat}
              />
            ) : (
              <div className="space-y-8">
                {safeMessages.map((m: Message, idx: number) => {
                  const isUser = m.role === 'user';
                  const blocks = isUser ? [{ type: 'markdown', content: m.content } as { type: 'markdown'; content: string; lang?: string }] : splitAssistantContent(m.content);
                  const isStreamingAgentMessage = !isUser && streamingForCurrentChat && idx === safeMessages.length - 1;

                  // Calculate clean content for copy (excluding logs)
                  const cleanContent = isUser ? m.content : blocks
                    .filter(b => b.type !== 'log')
                    .map(b => {
                      if (b.type === 'code') {
                        return '```' + (b.lang || '') + '\n' + b.content + '\n```';
                      }
                      return b.content;
                    })
                    .join('').trim();

                  // Determine if we should show the main copy button
                  // 1. Must have content
                  // 2. Should not be a "Thought" bubble (intermediate step)
                  // 3. Should not be an intermediate step (has stepInfo)
                  const isThought = !isUser && cleanContent.startsWith('Thought:');
                  const hasStepInfo = !isUser && !!m.stepInfo;
                  const showMainCopyButton = cleanContent && !isThought && !hasStepInfo;

                  const alignClass = isUser ? 'justify-end' : 'justify-start';
                  // isStreamingAgentMessage moved up
                  const eyeClass = isStreamingAgentMessage ? 'robot-eye robot-eye-blink' : 'robot-eye robot-eye-idle';
                  const rightEyeStyle = !isUser
                    ? (isStreamingAgentMessage ? undefined : { animationDelay: '1.8s' })
                    : undefined;

                  return (
                    <div key={idx} className="w-full flex flex-col group/message">
                      <div className={`flex ${alignClass} w-full`}>
                        {isUser ? (
                          // User message: display images and text separately
                          <div className="w-full max-w-3xl space-y-3 pl-8 md:pl-16">
                            {m.images && m.images.length > 0 && (
                              <div className="flex flex-wrap gap-3 justify-end">
                                {m.images.map((img, imgIdx) => (
                                  <div key={imgIdx} className="relative group animate-brutal-pop">
                                    <img
                                      src={`data:${img.mime_type};base64,${img.data}`}
                                      alt={img.filename}
                                      className="max-w-sm max-h-64 border-4 border-brutal-black shadow-brutal-lg object-contain bg-white"
                                      title={img.filename}
                                    />
                                    <div className="absolute bottom-0 left-0 right-0 bg-brutal-black text-brutal-white text-xs px-2 py-1 font-bold opacity-0 group-hover:opacity-100 transition-opacity duration-100">
                                      {img.filename}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                            {m.content && (
                              <div className="flex justify-end">
                                <div className="bg-brutal-yellow border-3 border-brutal-black shadow-brutal-lg px-5 py-4 max-w-full font-medium relative select-text">
                                  <div className="prose prose-sm max-w-none break-words text-brutal-black font-sans">{m.content}</div>
                                </div>
                              </div>
                            )}
                            <div className="text-[10px] font-bold text-neutral-400 uppercase text-right pr-1 opacity-0 group-hover/message:opacity-100 transition-opacity select-none">
                              User
                            </div>
                          </div>
                        ) : (
                          // Assistant message: Neo-brutalist white bubble with AI indicator
                          <div className={`group w-full max-w-4xl break-words overflow-visible space-y-0 text-sm leading-relaxed relative pr-4 md:pr-12`}>
                            {/* AI Assistant Label - Bold & Brutalist */}
                            <div className="inline-flex items-center gap-2 bg-brutal-black text-brutal-white px-3 py-1 font-bold text-xs tracking-wider border-3 border-brutal-black mb-0 shadow-[4px_4px_0_0_rgba(0,0,0,0.1)] relative pointer-events-none select-none">
                              <svg className={`w-4 h-4 ${isStreamingAgentMessage ? 'robot-streaming' : ''}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                <rect x="2" y="2" width="20" height="20" rx="3" fill="currentColor" />
                                <rect x="4" y="4" width="16" height="16" rx="3" fill="#000000" />
                                <rect className={eyeClass} x="5.5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                                <rect className={eyeClass} style={rightEyeStyle} x="13.5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                              </svg>
                              <span>AGENT</span>
                            </div>
                            <div className={`bg-white border-3 border-brutal-black px-6 py-5 space-y-4 relative -mt-3 pt-6 shadow-brutal-lg select-text`}>
                              {showMainCopyButton && <CopyButton text={cleanContent} className="absolute top-2 right-2 z-10" color="bg-brutal-yellow" />}
                              {/* Use StreamingMessageContent for the last message if it's streaming, otherwise render directly */
                                isStreamingAgentMessage ? (
                                  <StreamingMessageContent
                                    content={m.content}
                                    isStreaming={true}
                                    onBlockRender={(blocks) => (
                                      <>
                                        {blocks.map((b, bi) => {
                                          const blockKey = generateBlockKey(b, bi, idx);
                                          const isLastBlock = bi === blocks.length - 1;
                                          // Cursor always follows the typewriter trail
                                          const showCursor = isLastBlock;

                                          if (b.type === 'markdown') {
                                            // Append blinking cursor HTML
                                            const contentWithCursor = showCursor
                                              ? b.content + ' <span class="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>'
                                              : b.content;
                                            return <MarkdownRenderer key={blockKey} content={contentWithCursor} />;
                                          } else if (b.type === 'log') {
                                            return <LogBlock key={blockKey} title={b.title} content={b.content} />;
                                          } else {
                                            return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} isStreaming={showCursor} />;
                                          }
                                        })}
                                      </>
                                    )}
                                  />
                                ) : (
                                  blocks.map((b, bi) => {
                                    const blockKey = generateBlockKey(b, bi, idx);
                                    if (b.type === 'markdown') {
                                      return <MarkdownRenderer key={blockKey} content={b.content} />;
                                    } else if (b.type === 'log') {
                                      return <LogBlock key={blockKey} title={b.title} content={b.content} />;
                                    } else {
                                      return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} />;
                                    }
                                  })
                                )}
                              {/* end user/assistant content */}
                              {/* end user/assistant content */}
                            </div>
                          </div>
                        )}
                      </div>
                      {!isUser && m.stepInfo && (
                        <div className={`flex ${alignClass} w-full mt-2 pl-4`}>
                          <div className="inline-flex items-center gap-2 text-[10px] text-brutal-black font-mono font-bold px-3 py-1 bg-neutral-100 border-2 border-brutal-black shadow-sm select-none">
                            <span className="text-brutal-blue">⚡</span>
                            <span>{m.stepInfo}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {!configReady && (
              <div className="flex items-center justify-center p-4">
                <div className="bg-brutal-yellow border-2 border-brutal-black px-4 py-2 text-xs font-bold uppercase animate-pulse shadow-brutal-sm">
                  Connecting to Neural Core...
                </div>
              </div>
            )}
            <div ref={bottomRef} className="h-4" />
          </div>

          {/* Scroll to bottom button */}
          {showScrollButton && (
            <button
              onClick={scrollToBottom}
              className="absolute bottom-6 right-6 z-20 w-10 h-10 bg-brutal-black text-white border-2 border-white shadow-brutal-lg flex items-center justify-center hover:bg-brutal-blue transition-colors animate-brutal-pop"
              title="Scroll to bottom"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
            </button>
          )}
        </div>
        {safeMessages.length > 0 && (
          <div className="border-t-4 border-brutal-black p-4 flex flex-col gap-3 bg-neutral-100">
            {/* Plan Progress (Inline) */}
            {!isPlanDocked && (
              <PlanProgress
                plan={plan}
                isDocked={false}
                onToggleDock={() => setIsPlanDocked(true)}
                isExpanded={isPlanExpanded}
                onToggleExpand={() => setIsPlanExpanded(!isPlanExpanded)}
              />
            )}

            <ChatInputPanel
              input={input}
              setInput={setInput}
              selectedImages={selectedImages}
              handleImageSelect={handleImageSelect}
              removeImage={removeImage}
              send={send}
              isStreaming={isStreaming}
              config={safeConfig}
              setConfig={setConfig}
              backendConfig={safeBackendConfig}
              fileInputRef={fileInputRef}
              textareaRef={textareaRef}
              configReady={configReady}
              streamingForCurrentChat={streamingForCurrentChat}
              stopStreaming={stopStreaming}
              stopInFlight={stopInFlightRef.current}
              modelSelectDropUp={true}
            />
          </div>
        )}
      </div>

      {/* Right Sidebar - Plan Docked */}
      {isPlanDocked && (
        <div className="w-96 bg-white border-l-3 border-brutal-black z-10 flex flex-col shrink-0 transition-all duration-300">
          <div className="h-14 bg-brutal-yellow border-b-3 border-brutal-black flex items-center justify-between px-4 shrink-0">
            <span className="font-brutal font-bold text-sm tracking-wider uppercase">PLAN DETAILS</span>
            <button
              onClick={() => setIsPlanDocked(false)}
              className="w-8 h-8 flex items-center justify-center border-2 border-brutal-black bg-white hover:bg-black hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 bg-neutral-50/50 scrollbar-thin scrollbar-track-neutral-200 scrollbar-thumb-brutal-black">
            <PlanProgress
              plan={plan}
              isDocked={true}
              onToggleDock={() => setIsPlanDocked(false)}
              isExpanded={isPlanExpanded}
              onToggleExpand={() => setIsPlanExpanded(!isPlanExpanded)}
            />
          </div>
        </div>
      )}

    </div>
  );
};
