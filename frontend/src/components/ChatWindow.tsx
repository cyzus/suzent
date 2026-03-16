import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { useAGUI, type AGUIPart } from '../hooks/useAGUI';
import { getApiBase, getSandboxParams } from '../lib/api';
import type { Message, FileAttachment } from '../types/api';
import { isIntermediateStepContent, splitAssistantContent, mergeToolCallPairs, type ContentBlock } from '../lib/chatUtils';
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

// ── AGUIPart[] → Store Message conversion ────────────────────────────
function escapeHtmlForStore(unsafe: string): string {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatUsage(usage: any): string {
  if (!usage) return '';
  const fmt = (n: number) => n.toLocaleString();
  return `Input: ${fmt(usage.input_tokens)} | Output: ${fmt(usage.output_tokens)} | Total: ${fmt(usage.total_tokens)}`;
}

/**
 * Convert AG-UI streaming parts to a store Message for persistence.
 * Tool invocations are serialized as HTML <details> blocks with emoji conventions
 * so the existing historical message rendering pipeline can display them.
 */
function aguiPartsToStoreMessage(parts: AGUIPart[], usage?: any): Message {
  let content = '';
  for (const part of parts) {
    if (part.type === 'text') {
      content += part.text || '';
    } else if (part.type === 'reasoning') {
      const text = part.text || '';
      if (text) {
        content += `\n\n<details data-reasoning="true"><summary>Thinking</summary>\n\n${text}\n\n</details>\n\n`;
      }
    } else if (part.type === 'tool') {
      const toolName = part.toolName || 'unknown';
      const toolCallId = part.toolCallId || '';
      const argsStr = part.args || '';
      const approvalId = part.approvalId || '';
      const stateAttr = part.state === 'approval-requested' ? 'pending' : (part.state === 'error' ? 'denied' : '');
      const attrs = ` data-tool-call-id="${toolCallId}"` +
        (approvalId ? ` data-approval-id="${approvalId}"` : '') +
        (stateAttr ? ` data-approval-state="${stateAttr}"` : '');

      content += `\n\n<details${attrs}><summary>\u{1F527} ${toolName}</summary>\n\n<pre><code class="language-text">${escapeHtmlForStore(argsStr)}</code></pre>\n\n</details>\n\n`;
      if (part.output != null) {
        content += `\n\n<details data-tool-call-id="${toolCallId}"><summary>\u{1F4E6} ${toolName}</summary>\n\n<pre><code class="language-text">${escapeHtmlForStore(part.output)}</code></pre>\n\n</details>\n\n`;
      }
    }
  }
  return { role: 'assistant', content, timestamp: new Date().toISOString(), stepInfo: usage ? formatUsage(usage) : undefined };
}

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



// Message list component (renders historical / store messages only)
const MessageList: React.FC<{
  messages: Message[];
  isStreaming: boolean;
  streamingForCurrentChat: boolean;
  chatId?: string;
  onImageClick?: (src: string) => void;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: 'session' | null, toolName?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
}> = ({ messages, isStreaming, streamingForCurrentChat, chatId, onImageClick, onFileClick, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy }) => (
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
        if (m.role !== 'user' && isIntermediateStepContent(m.content, m.stepInfo)) {
          // Start of a step group — collect all consecutive intermediate step messages
          const groupStart = i;
          const allBlocks: ContentBlock[] = [];
          const allStepInfos: string[] = [];
          while (i < messages.length && messages[i].role !== 'user' && isIntermediateStepContent(messages[i].content, messages[i].stepInfo)) {
            const parsed = filterIgnored(splitAssistantContent(messages[i].content));
            // Include both tool calls and reasoning in the step blocks
            const stepBlocks = parsed.filter(b => b.type === 'toolCall' || b.type === 'reasoning');
            if (stepBlocks.length > 0) {
              allBlocks.push(...stepBlocks);
            }
            if (messages[i].stepInfo) allStepInfos.push(messages[i].stepInfo!);
            if (i > groupStart) skipIndices.add(i); // skip non-representative messages
            i++;
          }
          // Merge invocations with outputs for toolCalls; reasoning blocks pass through
          const merged = mergeToolCallPairs(allBlocks);

          // Also check if the next message is a content message — collect its stepInfo too
          if (i < messages.length && messages[i].role !== 'user' && !isIntermediateStepContent(messages[i].content, messages[i].stepInfo)) {
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

        // Intermediate step group representative: render merged pills (no badge here — shows after final answer)
        if (group) {
          return (
            <div key={idx} className="w-full flex flex-col group/message">
              <div className="flex justify-start w-full">
                <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
                  {group.mergedBlocks.map((b, bi) => {
                    if (b.type === 'toolCall') {
                      const isPending = b.approvalState === 'pending';
                      return (
                        <ToolCallBlock
                          key={`group-${idx}-${bi}`}
                          toolName={b.toolName || 'unknown'}
                          toolArgs={b.toolArgs}
                          output={b.content || undefined}
                          approvalState={b.approvalState as 'pending' | 'denied' | undefined}
                          onApprove={(isPending && b.approvalId && onToolApproval)
                            ? (remember) => onToolApproval(b.approvalId!, b.toolCallId || '', true, remember, b.toolName)
                            : undefined}
                          onDeny={(isPending && b.approvalId && onToolApproval)
                            ? () => onToolApproval(b.approvalId!, b.toolCallId || '', false, null, b.toolName)
                            : undefined}
                          defaultCollapsed={!isPending}
                        />
                      );
                    }
                    if (b.type === 'reasoning' && b.content.trim()) {
                      return (
                        <div key={`group-${idx}-${bi}`} className="pl-4 pr-6 py-1 border-l-2 border-neutral-200 ml-1">
                          <details className="group">
                            <summary className="text-xs italic text-neutral-500 font-medium cursor-pointer select-none hover:text-neutral-700 flex items-center gap-1">
                              <span className="truncate">{b.content.trim().split('\n')[0].trim() || 'Thinking'}</span>
                            </summary>
                            <div className="mt-1 p-2 bg-neutral-50/50 rounded border border-neutral-100">
                              <pre className="text-[11px] italic text-neutral-500 font-medium leading-snug whitespace-pre-wrap overflow-auto">
                                {b.content.trim()}
                              </pre>
                            </div>
                          </details>
                        </div>
                      );
                    }
                    return null;
                  })}
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
                  onToolApproval={onToolApproval}
                  toolApprovalPolicy={toolApprovalPolicy}
                  onRemoveApprovalPolicy={onRemoveApprovalPolicy}
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
  const HEARTBEAT_HEALTHY_WINDOW_MS = 18_000;

  const formatRelativeHeartbeatTime = (iso?: string): string | null => {
    if (!iso) return null;
    const timestamp = new Date(iso).getTime();
    if (Number.isNaN(timestamp)) return null;
    const deltaMs = Date.now() - timestamp;
    if (deltaMs < 0) return null;

    const deltaSec = Math.floor(deltaMs / 1000);
    if (deltaSec < 10) return 'just now';
    if (deltaSec < 60) return `${deltaSec}s ago`;

    const deltaMin = Math.floor(deltaSec / 60);
    if (deltaMin < 60) return `${deltaMin}m ago`;

    const deltaHours = Math.floor(deltaMin / 60);
    if (deltaHours < 24) return `${deltaHours}h ago`;

    const deltaDays = Math.floor(deltaHours / 24);
    return `${deltaDays}d ago`;
  };

  // Store hooks
  const {
    messages,
    addMessage,
    updateLastUserMessageImages,
    config,
    backendConfig,
    setConfig,
    shouldResetNext,
    consumeResetFlag,
    forceSaveNow,
    updateMessage,
    setIsStreaming,
    currentChatId,
    createNewChat,
    loadChat,
    isStreaming,
    activeStreamingChatId,
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
  const [currentUsage, setCurrentUsage] = useState<any>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const stopInFlightRef = useRef(false);
  // True while a steer is in flight — prevents the normal-send finally from hiding the bubble
  const steeringRef = useRef(false);

  // Ref for async callback access to current chatId
  const activeChatIdRef = useRef<string | null>(currentChatId);
  useEffect(() => { activeChatIdRef.current = currentChatId; }, [currentChatId]);

  // Ref to lock the chat ID for the current stream so switching chats doesn't misroute messages
  const streamingChatIdRef = useRef<string | null>(null);

  // Set to true when the backend signals HEARTBEAT_OK — onFinish should discard the message.
  const heartbeatOkRef = useRef(false);
  const heartbeatInFlightRef = useRef(false);
  const [heartbeatLastOkAt, setHeartbeatLastOkAt] = useState<string | null>(null);

  // ── AG-UI streaming hook ─────────────────────────────────────────────
  const {
    parts: streamingParts,
    sendMessage: sendAGUI,
    resumeStream,
    steerStream,
    stop: stopAGUIStream,
    clearParts,
    resolveApproval,
    pendingApprovalCount,
    addApprovalDecision,
    consumeApprovalDecisions,
  } = useAGUI({
    url: `${getApiBase()}/chat`,
    onFinish: (parts) => {
      const chatId = streamingChatIdRef.current || activeChatIdRef.current;

      const hasPendingApprovals = parts.some(
        p => p.type === 'tool' && p.state === 'approval-requested'
      );

      if (heartbeatOkRef.current) {
        // HEARTBEAT_OK: backend rolled back the messages; discard streamed content and reload.
        heartbeatInFlightRef.current = false;
        setHeartbeatLastOkAt(new Date().toISOString());
        heartbeatOkRef.current = false;
        setIsStreaming(false, chatId);
        streamingChatIdRef.current = null;
        clearParts();
        setCurrentUsage(null);
        // Reload chat from DB to reflect rolled-back state.
        setTimeout(() => { try { loadChat(chatId!); } catch { } }, 300);
        return;
      }

      // Stream paused for HITL approvals: keep transient parts visible and
      // wait for resume before persisting to the chat history.
      if (hasPendingApprovals) {
        setIsStreaming(false, chatId);
        if (heartbeatInFlightRef.current) {
          setHeartbeatLastOkAt(new Date().toISOString());
        }
        heartbeatInFlightRef.current = false;
        setCurrentUsage(null);
        return;
      }

      const storeMsg = aguiPartsToStoreMessage(parts, currentUsage);
      if (storeMsg.content.trim()) {
        addMessage(storeMsg, chatId);
      }
      setIsStreaming(false, chatId);
      if (heartbeatInFlightRef.current) {
        // Heartbeat ran but no heartbeat_ok signal — still record last run time.
        setHeartbeatLastOkAt(new Date().toISOString());
      }
      heartbeatInFlightRef.current = false;
      streamingChatIdRef.current = null;
      clearParts();
      setCurrentUsage(null);
      setTimeout(async () => {
        try { await forceSaveNow(chatId); } catch { }
      }, 200);
      try { loadCoreMemory(); loadStats(); } catch { }
    },
    onCustomEvent: (name, value) => {
      if (name === 'plan_refresh') {
        const chatId = streamingChatIdRef.current || activeChatIdRef.current;
        applyPlanSnapshot(value as any);
        refreshPlan(chatId);
      } else if (name === 'usage_update') {
        setCurrentUsage(value);
      } else if (name === 'heartbeat_ok') {
        // Backend signals that this heartbeat run was OK and messages were rolled back.
        setHeartbeatLastOkAt(new Date().toISOString());
        heartbeatOkRef.current = true;
      }
    },
    onError: (error) => {
      console.error('AG-UI error:', error);
      const chatId = streamingChatIdRef.current || activeChatIdRef.current;
      heartbeatInFlightRef.current = false;
      heartbeatOkRef.current = false;
      setIsStreaming(false, chatId);
      streamingChatIdRef.current = null;
      stopInFlightRef.current = false;
    },
  });

  // Listen for external message triggers (e.g. from Heartbeat "Run Now")
  useEffect(() => {
    const handler = (e: any) => {
      const { body, options } = e.detail || {};
      heartbeatInFlightRef.current = Boolean(body?.is_heartbeat);
      if (body) {
        sendAGUI(body, options).catch(err => {
          heartbeatInFlightRef.current = false;
          console.error('[ChatWindow] External sendAGUI failed:', err);
        });
      }
    };
    window.addEventListener('agui:send-message', handler);
    return () => window.removeEventListener('agui:send-message', handler);
  }, [sendAGUI]);

  // HITL: tool approval handler (Stateless Resume)
  // Batches multiple approval decisions and only sends to backend when all are decided.
  const handleToolApproval = useCallback(async (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: 'session' | null,
    toolName?: string
  ) => {
    const targetChatId = activeChatIdRef.current || currentChatId;
    if (!targetChatId) return;

    const updateApprovalStateInHistory = (id: string, state: 'approved' | 'denied') => {
      messages.forEach((m, idx) => {
        if (m.role === 'assistant' && m.content.includes(`data-approval-id="${id}"`)) {
          const finalContent = m.content.replace(
            new RegExp(`(<details[^>]*data-approval-id="${id}"[^>]*data-approval-state=")pending(")`),
            `$1${state}$2`
          );

          if (finalContent !== m.content) {
            updateMessage(idx, { content: finalContent }, targetChatId);
          }
        }
      });
    };

    // Optimistic UI: instantly hide buttons before the backend responds
    resolveApproval(approvalId, approved);

    // Also update historical messages in the store if they contain this approval
    const newState = approved ? 'approved' : 'denied';
    updateApprovalStateInHistory(approvalId, newState);

    // Accumulate decision; only send when all pending approvals are decided
    let allDecided = addApprovalDecision(approvalId, toolCallId, approved, remember, toolName);

    // If user chose session policy on this tool, apply that same decision to all
    // currently pending approvals of the same tool in this paused stream.
    if (remember === 'session' && toolName) {
      const linkedPending = streamingParts
        .filter(
          p =>
            p.type === 'tool' &&
            p.state === 'approval-requested' &&
            p.toolName === toolName &&
            p.approvalId &&
            p.approvalId !== approvalId &&
            p.toolCallId
        )
        .map(p => ({ approvalId: p.approvalId as string, toolCallId: p.toolCallId as string }));

      for (const linked of linkedPending) {
        resolveApproval(linked.approvalId, approved);
        updateApprovalStateInHistory(linked.approvalId, newState);
        allDecided = addApprovalDecision(
          linked.approvalId,
          linked.toolCallId,
          approved,
          null,
          toolName
        ) || allDecided;
      }
    }

    if (!allDecided) return; // Still waiting for more decisions

    // All approvals decided — batch and send
    const decisions = consumeApprovalDecisions();

    // If any decision had "remember: session", update the UI config.
    // The backend gets the new config immediately via the payload.
    let currentConfig = config || { model: '', agent: '', tools: [] };
    let hasPolicyUpdate = false;
    const policyUpdates: Record<string, string> = {};

    decisions.forEach(d => {
      if (d.remember === 'session' && d.toolName) {
        policyUpdates[d.toolName] = d.approved ? 'always_allow' : 'always_deny';
        hasPolicyUpdate = true;
      }
    });

    if (hasPolicyUpdate) {
      currentConfig = {
        ...currentConfig,
        tool_approval_policy: {
          ...(currentConfig.tool_approval_policy || {}),
          ...policyUpdates
        }
      };
      setConfig(currentConfig);
    }

    const resumeApprovals = decisions.map(d => ({
      request_id: d.approvalId,
      tool_call_id: d.toolCallId,
      approved: d.approved,
      remember: d.remember,
      tool_name: d.toolName,
    }));

    try {
      const payload: Record<string, unknown> = {
        message: "",
        config: currentConfig,
        chat_id: targetChatId,
        reset: false,
        resume_approvals: resumeApprovals,
      };

      setIsStreaming(true, targetChatId);
      streamingChatIdRef.current = targetChatId;
      stopInFlightRef.current = false;
      // Use resumeStream to preserve existing tool parts in the UI
      await resumeStream(payload);
    } catch (error) {
      console.error('Failed to resume with tool approval:', error);
    } finally {
      setIsStreaming(false, targetChatId);
      stopInFlightRef.current = false;
      setTimeout(async () => {
        try { await forceSaveNow(targetChatId); } catch { }
      }, 600);
    }
  }, [currentChatId, config, resumeStream, resolveApproval, addApprovalDecision, consumeApprovalDecisions, updateMessage, setIsStreaming, forceSaveNow, setConfig, messages, streamingParts]);

  // Remove a tool from the approval policy
  const handleRemoveApprovalPolicy = useCallback((toolName: string) => {
    setConfig(prev => {
      if (!prev.tool_approval_policy) return prev;
      const { [toolName]: _, ...rest } = prev.tool_approval_policy;
      return {
        ...prev,
        tool_approval_policy: rest
      };
    });
  }, [setConfig]);

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
  // Keep transient tool approvals attached to their source chat.
  // Without this guard, switching chats can render stale approval UI
  // from a different chat because AG-UI parts are kept for resume.
  const transientPartsChatId = streamingChatIdRef.current || activeStreamingChatId;
  const hasPendingTransientApprovals =
    transientPartsChatId === currentChatId &&
    streamingParts.some(p => p.type === 'tool' && p.state === 'approval-requested');
  const showTransientAssistant = streamingForCurrentChat || hasPendingTransientApprovals;
  const configReady = !!(safeBackendConfig && safeConfig.model && safeConfig.agent);

  const heartbeatEnabled = !!safeConfig.heartbeat_enabled;
  const heartbeatIsRunning = heartbeatEnabled && heartbeatInFlightRef.current && streamingForCurrentChat;
  const heartbeatLastSeen = heartbeatLastOkAt || safeConfig.heartbeat_last_run_at || null;
  const heartbeatLastSeenTs = heartbeatLastSeen ? new Date(heartbeatLastSeen).getTime() : 0;
  const heartbeatFresh = heartbeatEnabled && heartbeatLastSeenTs > 0 && (Date.now() - heartbeatLastSeenTs) <= HEARTBEAT_HEALTHY_WINDOW_MS;
  const heartbeatRelative = formatRelativeHeartbeatTime(heartbeatLastSeen || undefined);

  const heartbeatBadge = (() => {
    if (!heartbeatEnabled) {
      return {
        signClass: 'bg-neutral-200 dark:bg-zinc-700 text-neutral-500 dark:text-neutral-400',
        containerClass: 'bg-neutral-50 dark:bg-zinc-800 text-neutral-500 dark:text-neutral-400',
        text: t('chatWindow.heartbeatOff'),
        isBeating: false,
        fast: false,
        ekg: 'flat',
      };
    }

    if (heartbeatIsRunning) {
      return {
        signClass: 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black',
        containerClass: 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white bg-dot-pattern',
        text: t('chatWindow.heartbeatRunning'),
        isBeating: true,
        fast: true,
        ekg: 'active',
      };
    }

    if (heartbeatFresh) {
      return {
        signClass: 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black',
        containerClass: 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white',
        text: t('chatWindow.heartbeatHealthy'),
        isBeating: true,
        fast: false,
        ekg: 'active',
      };
    }

    return {
      signClass: 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white',
      containerClass: 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white',
      text: heartbeatRelative
        ? t('chatWindow.heartbeatLastRun', { time: heartbeatRelative })
        : t('chatWindow.heartbeatEnabled'),
      isBeating: false,
      fast: false,
      ekg: 'slow',
    };
  })();

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

  // Send message handler (also handles steering when streaming)
  const send = async () => {
    const prompt = input.trim();
    if (!prompt || !configReady || isUploading) return;

    // If currently streaming for this chat, steer instead of sending new message
    if (streamingForCurrentChat && currentChatId) {
      setInput('');
      addMessage({ role: 'user', content: prompt, timestamp: new Date().toISOString() }, currentChatId);

      steeringRef.current = true;
      try {
        await steerStream({
          chat_id: currentChatId,
          message: prompt,
          config: safeConfig,
        });
      } catch (error) {
        console.error('Error during steer:', error);
      } finally {
        steeringRef.current = false;
        setIsStreaming(false, currentChatId);
        stopInFlightRef.current = false;
        setTimeout(async () => {
          try { await forceSaveNow(currentChatId); } catch { }
        }, 600);
      }
      return;
    }

    // Normal send — not streaming
    if (isStreaming) return;

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
        return;
      }
    }

    // Upload successful - now clear input and files
    const resetFlag = shouldResetNext;
    if (resetFlag) consumeResetFlag();
    setInput('');
    clearFiles();
    setCurrentUsage(null);

    // Add user message to store for display + persistence
    addMessage({
      role: 'user',
      content: prompt,
      timestamp: new Date().toISOString(),
      images: imagePreviews,
      files: uploadedFileMetadata
    }, chatIdForSend);
    setIsStreaming(true, chatIdForSend);
    streamingChatIdRef.current = chatIdForSend;
    activeChatIdRef.current = chatIdForSend;
    stopInFlightRef.current = false;

    try {
      const payload: Record<string, unknown> = {
        message: prompt,
        config: safeConfig,
        chat_id: chatIdForSend,
        reset: resetFlag,
      };
      if (uploadedFileMetadata) {
        payload.files = uploadedFileMetadata;
      }

      if (imageFilesToSend.length > 0) {
        const formData = new FormData();
        formData.append('message', prompt);
        formData.append('config', JSON.stringify(safeConfig));
        formData.append('chat_id', chatIdForSend);
        formData.append('reset', String(resetFlag));
        for (const file of imageFilesToSend) {
          formData.append('files', file);
        }
        await sendAGUI(payload, { formData });
      } else {
        await sendAGUI(payload);
      }
    } catch (error) {
      console.error('Error during streaming:', error);
    } finally {
      // Safety net: onFinish/onError handle state, but ensure cleanup.
      // Skip if a steer is in progress — steer's own finally handles cleanup.
      if (!steeringRef.current) {
        setIsStreaming(false, chatIdForSend);
      }
      stopInFlightRef.current = false;
      setTimeout(async () => {
        try { await forceSaveNow(chatIdForSend); } catch { }
      }, 600);
    }
  };

  // Stop streaming handler
  const stopStreaming = async () => {
    if (!isStreaming || stopInFlightRef.current) return;
    stopInFlightRef.current = true;

    // Abort the AG-UI SSE connection
    stopAGUIStream();

    const targetChatId = activeStreamingChatId;
    if (!targetChatId) {
      stopInFlightRef.current = false;
      return;
    }

    try {
      const res = await fetch(`${getApiBase()}/chat/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: targetChatId, reason: 'User requested stop' })
      });
      if (!res.ok) {
        console.error('Stop request failed:', res.status, res.statusText);
      }
    } catch (error) {
      console.error('Error sending stop request:', error);
    }
    // Note: stopInFlightRef reset happens in onFinish/finally
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
      className="flex flex-row flex-1 h-full overflow-x-hidden bg-neutral-50 dark:bg-zinc-900 relative"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {isDragging && <DragOverlay />}

      {/* Main Chat Column */}
      <div className="flex flex-col flex-1 min-w-0 h-full relative">
        <div className="absolute top-2 right-6 z-30 pointer-events-none">
          <div
            className={`inline-flex items-center shadow-[2px_2px_0_0_#000] border-2 border-brutal-black font-bold uppercase tracking-wide pointer-events-auto cursor-default group transition-transform hover:-translate-y-0.5`}
            aria-live="polite"
            title={heartbeatBadge.text}
          >
            <div className={`flex items-center justify-center px-1.5 py-1 h-full border-r-2 border-brutal-black ${heartbeatBadge.signClass}`}>
              <svg 
                className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${heartbeatBadge.isBeating ? (heartbeatBadge.fast ? 'pixel-heart-beat-fast' : 'pixel-heart-beat') : ''}`}
                viewBox="0 0 24 24" 
                fill="currentColor"
              >
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
              </svg>
            </div>
            
            <div className={`px-2 py-1 flex items-center gap-1.5 ${heartbeatBadge.containerClass}`}>
              <div className="w-8 h-4 sm:w-10 sm:h-5 relative border-r-2 border-current pr-1 flex-shrink-0 opacity-80">
                <svg viewBox="0 0 100 50" preserveAspectRatio="none" className="w-full h-full">
                  {heartbeatBadge.ekg !== 'flat' ? (
                    <path
                      className={`ekg-active-wave ${heartbeatBadge.ekg === 'active' ? (heartbeatBadge.fast ? '[animation-duration:1.5s]' : '[animation-duration:3s]') : '[animation-duration:6s] opacity-50'}`}
                      pathLength="100"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="6"
                      d={heartbeatBadge.ekg === 'slow' ? "M 0 25 L 30 25 L 34 30 L 38 15 L 44 35 L 50 25 L 100 25" : "M 0 25 L 10 25 L 14 30 L 22 5 L 28 45 L 34 25 L 100 25"}
                    />
                  ) : (
                    <path
                      className="ekg-flatline"
                      pathLength="100"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="6"
                      d="M 0 25 L 100 25"
                    />
                  )}
                </svg>
              </div>
              <span className="text-[10px] sm:text-xs max-w-[120px] sm:max-w-[180px] truncate">{heartbeatBadge.text}</span>
            </div>
          </div>
        </div>

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
              <>
                <MessageList
                  messages={safeMessages}
                  isStreaming={isStreaming}
                  streamingForCurrentChat={streamingForCurrentChat}
                  chatId={currentChatId ?? undefined}
                  onImageClick={setViewingImage}
                  onFileClick={handleFileClick}
                  onToolApproval={handleToolApproval}
                  toolApprovalPolicy={safeConfig.tool_approval_policy}
                  onRemoveApprovalPolicy={handleRemoveApprovalPolicy}
                />
                {/* Streaming/transient assistant message from AG-UI */}
                {showTransientAssistant && (
                  <div className="space-y-6 mt-6">
                    <div className="w-full flex flex-col group/message">
                      <div className="flex justify-start w-full">
                        <AssistantMessage
                          message={{ role: 'assistant', content: '' }}
                          messageIndex={safeMessages.length}
                          isStreaming={streamingForCurrentChat}
                          isLastMessage={true}
                          onFileClick={handleFileClick}
                          aguiParts={streamingParts}
                          onToolApproval={handleToolApproval}
                          usage={currentUsage}
                          toolApprovalPolicy={safeConfig.tool_approval_policy}
                          onRemoveApprovalPolicy={handleRemoveApprovalPolicy}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

            {!configReady && <LoadingIndicator />}
            <div ref={bottomRef} className="h-4" />
          </div>

          {showScrollButton && <ScrollToBottomButton onClick={scrollToBottom} />}
        </div>

        {/* Input Panel (shown when messages exist) */}
        {safeMessages.length > 0 && (
          <div className="p-4 flex flex-col gap-3 bg-neutral-50 dark:bg-zinc-900 z-30">
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
