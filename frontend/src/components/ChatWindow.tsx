import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { streamChat } from '../lib/streaming';
import { getApiBase, getSandboxParams } from '../lib/api';
import type { Message, FileAttachment } from '../types/api';
import { isToolOnlyContent, splitAssistantContent, mergeToolCallPairs, type ContentBlock } from '../lib/chatUtils';
import { usePlan } from '../hooks/usePlan';
import { useMemory } from '../hooks/useMemory';
import { useAutoScroll } from '../hooks/useAutoScroll';
import { useUnifiedFileUpload } from '../hooks/useUnifiedFileUpload';
import { PlanProgress } from './PlanProgress';
import { NewChatView } from './NewChatView';
import { ChatInputPanel } from './ChatInputPanel';
import { ImageViewer } from './ImageViewer';
import { FileViewer } from './FileViewer';
import { UserMessage, AssistantMessage, ToolCallBlock, RightSidebar } from './chat';
import { useI18n } from '../i18n';

// Drag overlay component
const DragOverlay: React.FC = () => {
  const { t } = useI18n();
  return (
    <div className="absolute inset-0 z-50 bg-brutal-blue/20 border-4 border-dashed border-brutal-black flex items-center justify-center pointer-events-none">
      <div className="bg-brutal-yellow border-4 border-brutal-black shadow-brutal-xl px-8 py-6 flex flex-col items-center gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-brutal-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
        </svg>
        <span className="text-lg font-bold text-brutal-black uppercase">{t('chatWindow.dragDropTitle')}</span>
        <span className="text-sm text-brutal-black">{t('chatWindow.dragDropDesc')}</span>
      </div>
    </div>
  );
};

// Scroll to bottom button
const ScrollToBottomButton: React.FC<{ onClick: () => void }> = ({ onClick }) => {
  const { t } = useI18n();
  return (
    <button
      onClick={onClick}
      className="absolute bottom-6 right-6 z-20 w-10 h-10 bg-brutal-black text-white border-2 border-white shadow-brutal-lg flex items-center justify-center hover:bg-brutal-blue transition-colors animate-brutal-pop"
      title={t('chatWindow.scrollToBottom')}
    >
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
      </svg>
    </button>
  );
};

// Loading indicator
const LoadingIndicator: React.FC = () => {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center p-4">
      <div className="bg-brutal-yellow border-2 border-brutal-black px-4 py-2 text-xs font-bold uppercase animate-pulse shadow-brutal-sm">
        {t('chatWindow.connecting')}
      </div>
    </div>
  );
};



// Message list component
const MessageList: React.FC<{
  messages: Message[];
  isStreaming: boolean;
  streamingForCurrentChat: boolean;
  chatId?: string;
  hideToolCalls?: boolean;
  onImageClick?: (src: string) => void;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ messages, isStreaming, streamingForCurrentChat, chatId, hideToolCalls, onImageClick, onFileClick }) => (
  <div className="space-y-6">
    {(() => {
      // Pre-compute tool-only groups: consecutive tool-only assistant messages
      // are rendered as a single merged pill group instead of individual messages
      const IGNORED_TOOL_NAMES = ['final_answer', 'final answer'];

      const filterIgnored = (blocks: ContentBlock[]) =>
        blocks.filter(b => {
          if (b.type !== 'toolCall') return true;
          return !IGNORED_TOOL_NAMES.includes((b.toolName || '').toLowerCase());
        });

      // Build a set of message indices that belong to tool-only groups
      // and determine which index is the "representative" that renders the merged pills
      const skipIndices = new Set<number>();
      const groupRenders = new Map<number, { mergedBlocks: ContentBlock[]; stepSummary: string | null }>();

      let i = 0;
      while (i < messages.length) {
        const m = messages[i];
        if (m.role !== 'user' && isToolOnlyContent(m.content)) {
          // Start of a tool-only group — collect all consecutive tool-only messages
          const groupStart = i;
          const allBlocks: ContentBlock[] = [];
          const allStepInfos: string[] = [];
          while (i < messages.length && messages[i].role !== 'user' && isToolOnlyContent(messages[i].content)) {
            const parsed = filterIgnored(splitAssistantContent(messages[i].content));
            allBlocks.push(...parsed.filter(b => b.type === 'toolCall'));
            if (messages[i].stepInfo) allStepInfos.push(messages[i].stepInfo!);
            if (i > groupStart) skipIndices.add(i); // skip non-representative messages
            i++;
          }
          // Merge invocations with outputs across all messages in the group
          const merged = mergeToolCallPairs(allBlocks);

          // Also check if the next message is a content message — collect its stepInfo too
          if (i < messages.length && messages[i].role !== 'user' && !isToolOnlyContent(messages[i].content)) {
            if (messages[i].stepInfo) allStepInfos.push(messages[i].stepInfo!);
          }

          let stepSummary: string | null = null;
          if (allStepInfos.length > 0) {
            let totalInput = 0;
            let totalOutput = 0;
            for (const info of allStepInfos) {
              const inputMatch = info.match(/Input\s+tokens:\s+([\d,]+)/i);
              const outputMatch = info.match(/Output\s+tokens:\s+([\d,]+)/i);
              if (inputMatch) totalInput += parseInt(inputMatch[1].replace(/,/g, ''), 10);
              if (outputMatch) totalOutput += parseInt(outputMatch[1].replace(/,/g, ''), 10);
            }
            const fmtNum = (n: number) => n.toLocaleString();
            stepSummary = `${allStepInfos.length} steps | Input: ${fmtNum(totalInput)} tokens | Output: ${fmtNum(totalOutput)} tokens`;
          }

          groupRenders.set(groupStart, { mergedBlocks: merged, stepSummary });
        } else {
          i++;
        }
      }

      return messages.map((m, idx) => {
        if (skipIndices.has(idx)) return null; // Part of a group, rendered by representative

        const isUser = m.role === 'user';
        const isLastMessage = idx === messages.length - 1;
        const isAssistant = !isUser;
        const group = groupRenders.get(idx);

        // Tool-only group representative: render merged pills + step summary
        if (group) {
          return (
            <div key={idx} className="w-full flex flex-col group/message">
              <div className="flex justify-start w-full">
                <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
                  {group.mergedBlocks.map((b, bi) => (
                    b.type === 'toolCall' ? (
                      <ToolCallBlock
                        key={`group-${idx}-${bi}`}
                        toolName={b.toolName || 'unknown'}
                        toolArgs={b.toolArgs}
                        output={b.content || undefined}
                        defaultCollapsed={hideToolCalls}
                      />
                    ) : null
                  ))}
                </div>
              </div>
            </div>
          );
        }

        // Regular message rendering
        // For content messages after a tool-only group, show the group's step summary
        const precedingGroup = isAssistant && !isUser ? (() => {
          for (let j = idx - 1; j >= 0; j--) {
            if (groupRenders.has(j)) return groupRenders.get(j)!;
            if (skipIndices.has(j)) continue;
            break;
          }
          return null;
        })() : null;

        const stepSummary = precedingGroup?.stepSummary || null;

        return (
          <div key={idx} className="w-full flex flex-col group/message">
            <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} w-full`}>
              {isUser ? (
                <UserMessage message={m} chatId={chatId} onImageClick={onImageClick} onFileClick={onFileClick} />
              ) : (
                <AssistantMessage
                  message={m}
                  messageIndex={idx}
                  isStreaming={streamingForCurrentChat}
                  isLastMessage={isLastMessage}
                  onFileClick={onFileClick}
                  hideToolCalls={hideToolCalls}
                />
              )}
            </div>
            {isAssistant && stepSummary && (
              <div className="flex justify-start w-full mt-2 pl-4">
                <div className="inline-flex items-center gap-2 text-[10px] text-brutal-black font-mono font-bold px-3 py-1 bg-neutral-100 border-2 border-brutal-black shadow-sm select-none">
                  <span className="text-brutal-blue">⚡</span>
                  <span>{stepSummary}</span>
                </div>
              </div>
            )}
          </div>
        );
      });
    })()}
  </div>
);

interface ChatWindowProps {
  isRightSidebarOpen?: boolean;
  onRightSidebarToggle?: (isOpen: boolean) => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  isRightSidebarOpen = false,
  onRightSidebarToggle = () => { }
}) => {
  // Store hooks
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
    hideToolCalls,
  } = useChatStore();

  const { refresh: refreshPlan, applySnapshot: applyPlanSnapshot, plan } = usePlan();
  const { loadCoreMemory, loadStats } = useMemory();
  const { t } = useI18n();

  // Local state
  const [input, setInput] = useState('');
  const [isPlanExpanded, setIsPlanExpanded] = useState(true);
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<{ path: string; name: string } | null>(null);
  const [sidebarFilePreview, setSidebarFilePreview] = useState<{ path: string; name: string } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const stopInFlightRef = useRef(false);

  // Custom hooks
  const {
    selectedFiles,
    isDragging,
    fileInputRef,
    handleFileSelect,
    handlePaste,
    removeFile,
    clearFiles,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    uploadFiles,
    uploadProgress,
    isUploading,
    error: fileError,
  } = useUnifiedFileUpload();

  // Safe values
  const safeMessages = messages || [];
  const safeConfig = config || { model: '', agent: '', tools: [] };
  const safeBackendConfig = backendConfig || null;
  const streamingForCurrentChat = isStreaming && activeStreamingChatId === currentChatId;
  const configReady = !!(safeBackendConfig && safeConfig.model && safeConfig.agent);

  // Auto-scroll
  const { scrollContainerRef, bottomRef, showScrollButton, scrollToBottom } = useAutoScroll(
    [safeMessages, isStreaming]
  );

  // Refresh plan when chat changes
  useEffect(() => {
    refreshPlan(currentChatId);
  }, [currentChatId, refreshPlan]);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input, isRightSidebarOpen, isPlanExpanded]);

  // Send message handler
  const send = async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming || !configReady || isUploading) return;

    // Create chat if needed
    let chatIdForSend = currentChatId;
    if (!chatIdForSend) {
      chatIdForSend = await createNewChat();
      if (!chatIdForSend) {
        console.error('Unable to initialize chat before sending message.');
        return;
      }
    }

    const filesToSend = [...selectedFiles];
    const imageFilesToSend = filesToSend.filter(f => f.type.startsWith('image/'));

    // Upload all files to server + generate base64 for images
    let uploadedFileMetadata: FileAttachment[] | undefined;
    let imagePreviews;

    if (filesToSend.length > 0) {
      try {
        const { fileMetadata, imagePreviews: imagePreviewData } = await uploadFiles(filesToSend, chatIdForSend);
        uploadedFileMetadata = fileMetadata;
        imagePreviews = imagePreviewData.length > 0 ? imagePreviewData : undefined;
      } catch (error) {
        console.error('Error uploading files:', error);
        // Don't proceed if file upload fails - keep input and files so user can retry
        return;
      }
    }

    // Upload successful - now clear input and files
    const resetFlag = shouldResetNext;
    if (resetFlag) consumeResetFlag();
    setInput('');
    clearFiles();

    addMessage({
      role: 'user',
      content: prompt,
      images: imagePreviews,
      files: uploadedFileMetadata
    }, chatIdForSend);
    setIsStreaming(true, chatIdForSend);
    stopInFlightRef.current = false;

    try {
      await streamChat(
        prompt,
        safeConfig,
        {
          onDelta: (partial) => updateAssistantStreaming(partial, chatIdForSend),
          onAction: () => { },
          onNewAssistantMessage: () => newAssistantMessage(chatIdForSend),
          onStepComplete: (stepInfo) => setStepInfo(stepInfo, chatIdForSend),
          onImagesProcessed: (processedImages) => {
            updateLastUserMessageImages(processedImages, chatIdForSend);
          },
          onPlanUpdate: (snapshot) => {
            applyPlanSnapshot(snapshot);
            refreshPlan(chatIdForSend);
          },
          onStreamComplete: () => {
            setIsStreaming(false, chatIdForSend);
            setTimeout(async () => {
              try {
                await forceSaveNow(chatIdForSend);
              } catch (error) {
                console.error('Error in forceSaveNow:', error);
              }
            }, 200);
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
        imageFilesToSend.length > 0 ? imageFilesToSend : undefined,
        uploadedFileMetadata
      );
    } catch (error) {
      console.error('Error during streaming:', error);
    } finally {
      setIsStreaming(false, chatIdForSend);
      setTimeout(async () => {
        try {
          await forceSaveNow(chatIdForSend);
        } catch (error) {
          console.error('Error in forceSaveNow:', error);
        }
      }, 600);
      stopInFlightRef.current = false;
    }
  };

  // Stop streaming handler
  const stopStreaming = async () => {
    if (!isStreaming || stopInFlightRef.current) return;
    stopInFlightRef.current = true;

    const targetChatId = activeStreamingChatId;
    if (!targetChatId) {
      stopInFlightRef.current = false;
      return;
    }

    try {
      const res = await fetch('/chat/stop', {
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

  // Handle file click from chat messages
  const handleFileClick = async (path: string, name: string, shiftKey?: boolean) => {
    // Let the click animation finish first
    await new Promise(resolve => setTimeout(resolve, 150));

    // Check if file exists before opening (silently fail if not)
    try {
      // Use helper to include volumes in existence check
      const queryParams = getSandboxParams(currentChatId || '', path, config.sandbox_volumes);
      const response = await fetch(`${getApiBase()}/sandbox/serve?${queryParams}`, {
        method: 'HEAD'
      });

      if (!response.ok) {
        // File doesn't exist - do nothing (animation already played)
        return;
      }

      if (shiftKey) {
        // Shift+Click: Open full-screen modal directly
        setViewingFile({ path, name });
      } else {
        // Normal click: Open in right sidebar
        setSidebarFilePreview({ path, name });
        if (!isRightSidebarOpen) {
          onRightSidebarToggle(true);
        }
      }
    } catch (error) {
      // Error checking file - do nothing (animation already played)
    }
  };

  // Handle maximize button from sidebar
  const handleMaximizeFile = (path: string, name: string) => {
    setViewingFile({ path, name });
  };

  return (
    <div
      className="flex flex-row flex-1 h-full overflow-x-hidden bg-neutral-50 relative"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {isDragging && <DragOverlay />}

      {/* Main Chat Column */}
      <div className="flex flex-col flex-1 min-w-0 h-full relative">
        <div className="relative flex-1 min-h-0">
          <div
            ref={scrollContainerRef}
            className={safeMessages.length === 0
              ? "h-full overflow-hidden p-4 md:p-6 pb-6"
              : "h-full overflow-y-auto overflow-x-hidden p-4 md:p-6 pb-6 scrollbar-thin"
            }
          >
            {safeMessages.length === 0 ? (
              <NewChatView
                input={input}
                setInput={setInput}
                selectedFiles={selectedFiles}
                handleFileSelect={handleFileSelect}
                removeFile={removeFile}
                uploadProgress={uploadProgress}
                isUploading={isUploading}
                fileError={fileError}
                send={send}
                isStreaming={isStreaming}
                config={safeConfig}
                setConfig={setConfig}
                backendConfig={safeBackendConfig}
                fileInputRef={fileInputRef}
                textareaRef={textareaRef}
                configReady={configReady}
                streamingForCurrentChat={streamingForCurrentChat}
                onPaste={handlePaste}
                onImageClick={setViewingImage}
              />
            ) : (
              <MessageList
                messages={safeMessages}
                isStreaming={isStreaming}
                streamingForCurrentChat={streamingForCurrentChat}
                chatId={currentChatId ?? undefined}
                hideToolCalls={hideToolCalls}
                onImageClick={setViewingImage}
                onFileClick={handleFileClick}
              />
            )}

            {!configReady && <LoadingIndicator />}
            <div ref={bottomRef} className="h-4" />
          </div>

          {showScrollButton && <ScrollToBottomButton onClick={scrollToBottom} />}
        </div>

        {/* Input Panel (shown when messages exist) */}
        {safeMessages.length > 0 && (
          <div className="p-4 flex flex-col gap-3 bg-neutral-50 z-30">
            {!isRightSidebarOpen && (
              <PlanProgress
                plan={plan}
                isDocked={false}
                onToggleDock={() => onRightSidebarToggle(!isRightSidebarOpen)}
                isExpanded={isPlanExpanded}
                onToggleExpand={() => setIsPlanExpanded(!isPlanExpanded)}
                isSidebarOpen={isRightSidebarOpen}
              />
            )}

            <ChatInputPanel
              input={input}
              setInput={setInput}
              selectedFiles={selectedFiles}
              handleFileSelect={handleFileSelect}
              removeFile={removeFile}
              uploadProgress={uploadProgress}
              isUploading={isUploading}
              fileError={fileError}
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
              onPaste={handlePaste}
              onImageClick={setViewingImage}
            />
          </div>
        )}
      </div>

      {/* Right Sidebar */}
      <RightSidebar
        isOpen={isRightSidebarOpen}
        onClose={() => onRightSidebarToggle(false)}
        plan={plan}
        isPlanExpanded={isPlanExpanded}
        onTogglePlanExpand={() => setIsPlanExpanded(!isPlanExpanded)}
        fileToPreview={sidebarFilePreview}
        onMaximizeFile={handleMaximizeFile}
      />

      <ImageViewer
        src={viewingImage}
        onClose={() => setViewingImage(null)}
      />

      <FileViewer
        filePath={viewingFile?.path ?? null}
        fileName={viewingFile?.name ?? null}
        chatId={currentChatId}
        onClose={() => setViewingFile(null)}
      />
    </div>
  );
};
