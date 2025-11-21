import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { streamChat } from '../lib/streaming';
import type { Message } from '../types/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import rehypePrism from 'rehype-prism-plus';
import { usePlan } from '../hooks/usePlan';
import { useMemory } from '../hooks/useMemory';

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
      className="absolute top-2 right-2 text-[11px] px-2 py-1 bg-brutal-green border-2 border-brutal-black shadow-brutal-sm hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-none transition-all duration-100 text-brutal-black font-bold uppercase"
      title="Copy code"
      type="button"
    >{copied ? 'Copied!' : 'Copy'}</button>
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

  // Sanitize fenced code block info strings so rehype-prism-plus never
  // receives an invalid language token which causes it to throw (for
  // example incoming fences like ```<body> or malformed tokens). We only
  // allow a known whitelist of language identifiers; otherwise we remove
  // the info string so the highlighter treats the block as plain text.
  const allowedLanguages = new Set([
    'python','javascript','typescript','java','cpp','c','go','rust','sql','html','css','json','yaml','xml','bash','shell','powershell','php','ruby','swift','kotlin','dart','r','matlab','scala','perl','lua','haskell','clojure','elixir','erlang','fsharp','ocaml','pascal','fortran','cobol','assembly','asm','text','plain'
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
    <div className="prose tight-lists prose-sm max-w-none break-words">
      <RM
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, rehypePrism]}
        components={{
          code(codeProps: any) {
            const { inline, className, children, ...rest } = codeProps;
            // More robust language extraction with validation
            const match = /language-([a-zA-Z0-9_-]+)/.exec(className || '');
            const lang = match ? match[1] : null;
            
            if (!inline && lang) {
              // Validate and clean the language name
              const cleanLang = lang.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
              const safeClassName = cleanLang ? `language-${cleanLang}` : 'language-text';

              return (
                <pre className="max-w-3xl overflow-x-auto text-xs bg-brutal-code-bg text-brutal-code-text border-3 border-brutal-black p-3 font-mono leading-relaxed break-words">
                  <code className={safeClassName}>{String(children)}</code>
                </pre>
              );
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
          blockquote(p: any) { return <blockquote className="border-l-4 border-brand-600/30 pl-3 italic text-neutral-600 break-words">{p.children}</blockquote>; }
        }}
      >
  {sanitized}
      </RM>
    </div>
  );
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
  const { refresh: refreshPlan, applySnapshot: applyPlanSnapshot } = usePlan();
  const { loadCoreMemory, loadStats } = useMemory();
  const [input, setInput] = useState('');
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
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

  const configReady = safeBackendConfig && safeConfig.model && safeConfig.agent;

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
            try { loadCoreMemory(); loadStats(); } catch {}
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
      className="flex flex-col flex-1 h-full overflow-hidden bg-neutral-50 relative"
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
      
      <div className="relative flex-1 min-h-0">
        <div ref={scrollContainerRef} className="h-full overflow-y-auto p-4 md:p-6 pb-6 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-neutral-300/80">
          {safeMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8 animate-brutal-drop">
              <div className="w-20 h-20 bg-brutal-black text-white flex items-center justify-center mb-6 border-4 border-brutal-black shadow-brutal-lg rotate-3 hover:rotate-0 transition-transform duration-300">
                <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h2 className="text-3xl font-brutal font-bold uppercase mb-2 text-brutal-black tracking-tight">System Ready</h2>
              <p className="text-neutral-600 max-w-md font-mono text-xs mb-8 bg-white px-3 py-1 border-2 border-brutal-black shadow-brutal-sm">
                // WAITING_FOR_INPUT...
              </p>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl w-full">
                {['Help me plan a project', 'Analyze this code', 'Search the web', 'Write a story'].map((suggestion, i) => (
                  <button
                    key={i}
                    onClick={() => setInput(suggestion)}
                    className="p-4 bg-white border-3 border-brutal-black shadow-brutal hover:translate-x-[-2px] hover:translate-y-[-2px] hover:shadow-brutal-lg active:translate-x-[0px] active:translate-y-[0px] active:shadow-brutal transition-all text-left font-bold uppercase text-sm group relative overflow-hidden"
                  >
                    <div className="absolute inset-0 bg-brutal-yellow translate-y-full group-hover:translate-y-0 transition-transform duration-200 z-0"></div>
                    <span className="relative z-10 flex items-center justify-between">
                      {suggestion}
                      <span className="text-brutal-black opacity-0 group-hover:opacity-100 transition-opacity">►</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-8">
              {safeMessages.map((m: Message, idx: number) => {
              const isUser = m.role === 'user';
              const blocks = isUser ? [{ type: 'markdown', content: m.content } as { type: 'markdown'; content: string; lang?: string }] : splitAssistantContent(m.content);
              
              const alignClass = isUser ? 'justify-end' : 'justify-start';
              const isStreamingAgentMessage = !isUser && streamingForCurrentChat && idx === safeMessages.length - 1;
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
                            <div className="bg-brutal-yellow border-3 border-brutal-black shadow-brutal-lg px-5 py-4 max-w-full font-medium animate-brutal-slide relative">
                              <div className="prose prose-sm max-w-none break-words text-brutal-black font-sans">{m.content}</div>
                            </div>
                          </div>
                        )}
                        <div className="text-[10px] font-bold text-neutral-400 uppercase text-right pr-1 opacity-0 group-hover/message:opacity-100 transition-opacity">
                          User
                        </div>
                      </div>
                    ) : (
                      // Assistant message: Neo-brutalist white bubble with AI indicator
                      <div className={`group w-full max-w-4xl break-words overflow-visible space-y-0 text-sm leading-relaxed relative pr-4 md:pr-12`}>
                        {/* AI Assistant Label - Bold & Brutalist */}
                        <div className="inline-flex items-center gap-2 bg-brutal-black text-brutal-white px-3 py-1 font-bold text-xs tracking-wider border-3 border-brutal-black mb-0 animate-brutal-pop shadow-[4px_4px_0_0_rgba(0,0,0,0.1)] z-10 relative">
                          <svg className={`w-4 h-4 ${isStreamingAgentMessage ? 'robot-streaming' : ''}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <rect x="2" y="2" width="20" height="20" rx="3" fill="currentColor" />
                            <rect x="4" y="4" width="16" height="16" rx="3" fill="#000000" />
                            <rect className={eyeClass} x="5.5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                            <rect className={eyeClass} style={rightEyeStyle} x="13.5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                          </svg>
                          <span>AGENT</span>
                        </div>
                        <div className="bg-white border-3 border-brutal-black shadow-brutal-lg px-6 py-5 space-y-4 animate-brutal-drop relative z-0 -mt-3 pt-6">
                        {blocks.map((b, bi) => b.type === 'markdown' ? (
                          <MarkdownRenderer key={bi} content={b.content} />
                        ) : (
                          <div key={bi} className="relative my-4 group/code">
                            <div className="absolute -top-3 left-4 bg-brutal-black text-white text-[10px] font-bold px-2 py-0.5 uppercase tracking-wider border-2 border-brutal-black z-10">
                              {(b as any).lang || 'CODE'}
                            </div>
                            <CopyButton text={b.content} />
                            <pre className="max-w-full overflow-x-auto text-xs bg-brutal-code-bg text-brutal-code-text border-3 border-brutal-black p-4 pt-6 font-mono leading-relaxed shadow-brutal-sm">
                              <code className={`language-${((b as any).lang || 'text').replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase() || 'text'}`}>{b.content}</code>
                            </pre>
                          </div>
                        ))}
                        {/* end user/assistant content */}
                        {idx === safeMessages.length - 1 && streamingForCurrentChat && (
                          <div className="flex gap-2 items-center text-xs font-bold text-brutal-black animate-pulse mt-2 p-2 bg-neutral-100 border-2 border-neutral-200 inline-block">
                            <div className="w-2 h-2 bg-brutal-black animate-bounce"></div>
                            <div className="w-2 h-2 bg-brutal-black animate-bounce" style={{animationDelay: '0.1s'}}></div>
                            <div className="w-2 h-2 bg-brutal-black animate-bounce" style={{animationDelay: '0.2s'}}></div>
                            <span className="ml-1">PROCESSING</span>
                          </div>
                        )}
                        </div>
                      </div>
                    )}
                  </div>
                  {!isUser && m.stepInfo && (
                    <div className={`flex ${alignClass} w-full mt-2 pl-4`}>
                      <div className="inline-flex items-center gap-2 text-[10px] text-brutal-black font-mono font-bold px-3 py-1 bg-neutral-100 border-2 border-brutal-black shadow-sm">
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
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="border-t-4 border-brutal-black p-4 flex flex-col gap-3 bg-neutral-100">
        {/* Image preview section */}
        {selectedImages.length > 0 && (
          <div className="flex flex-wrap gap-2 p-3 bg-brutal-white border-3 border-brutal-black shadow-brutal-sm">
            {selectedImages.map((file, idx) => (
              <div key={idx} className="relative group">
                <img
                  src={URL.createObjectURL(file)}
                  alt={file.name}
                  className="w-20 h-20 object-cover border-3 border-brutal-black"
                />
                <button
                  type="button"
                  onClick={() => removeImage(idx)}
                  className="absolute -top-2 -right-2 w-6 h-6 bg-brutal-red border-2 border-brutal-black text-white text-sm flex items-center justify-center font-bold shadow-brutal-sm hover:shadow-none transition-all"
                  title="Remove image"
                >
                  ×
                </button>
                <div className="absolute bottom-0 left-0 right-0 bg-brutal-black text-brutal-white text-[10px] px-1 py-0.5 truncate font-bold">
                  {file.name}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Input area with clean grid layout */}
        <div className="flex flex-col gap-2">
          <textarea
            ref={textareaRef}
            className="w-full resize-none overflow-y-auto min-h-[80px] max-h-[200px] bg-brutal-white border-3 border-brutal-black focus:outline-none focus:ring-4 focus:ring-brutal-yellow px-4 py-3 text-sm placeholder-neutral-400 font-medium placeholder:font-bold placeholder:uppercase transition-shadow scrollbar-thin scrollbar-track-transparent scrollbar-thumb-neutral-400"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!isStreaming && configReady && input.trim()) {
                  send();
                }
              }
            }}
            placeholder={configReady ? 'TYPE YOUR MESSAGE HERE...' : 'SYSTEM LOADING...'}
            disabled={!configReady}
          />

          {/* Button row */}
          <div className="flex gap-2 items-center justify-between">
            <div className="flex gap-2 items-center">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={handleImageSelect}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="h-12 px-4 bg-brutal-white border-3 border-brutal-black shadow-brutal hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-brutal-sm active:translate-x-[4px] active:translate-y-[4px] active:shadow-none transition-all duration-100 disabled:opacity-40 disabled:cursor-not-allowed font-bold uppercase text-xs flex items-center gap-2"
                title="Attach images"
                disabled={!configReady || isStreaming}
              >
                <svg className="w-5 h-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="2" width="12" height="12" />
                  <circle cx="6" cy="6" r="1.5" fill="currentColor" />
                  <polyline points="4,12 7,9 9,11 12,8 14,10" strokeLinecap="square" />
                </svg>
                <span className="hidden sm:inline">IMAGE</span>
              </button>
            </div>

            <div className="flex gap-3 items-center">
              <div className="text-[10px] text-brutal-black font-mono font-bold select-none uppercase opacity-50 hidden sm:block">
                ↵ SEND • ⇧↵ NEW LINE
              </div>

              <div className="flex gap-2">
                {streamingForCurrentChat && (
                  <button
                    type="button"
                    onClick={stopStreaming}
                    className="h-12 bg-brutal-red border-3 border-brutal-black shadow-brutal hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-brutal-sm active:translate-x-[4px] active:translate-y-[4px] active:shadow-none transition-all duration-100 px-5 text-xs font-bold disabled:opacity-60 disabled:cursor-not-allowed text-white uppercase"
                    disabled={stopInFlightRef.current}
                  >
                    STOP
                  </button>
                )}
                <button
                  type="submit"
                  className="h-12 bg-brutal-blue border-3 border-brutal-black shadow-brutal hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-brutal-sm active:translate-x-[4px] active:translate-y-[4px] active:shadow-none transition-all duration-100 px-6 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase"
                  disabled={isStreaming || !configReady}
                >
                  {streamingForCurrentChat ? 'SENDING...' : 'SEND'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
};
