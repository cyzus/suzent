import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { useAGUI, type AGUIPart } from '../hooks/useAGUI';
import { getApiBase, getSandboxParams } from '../lib/api';
import type { Message, FileAttachment } from '../types/api';
import type { ContentBlock } from '../lib/chatUtils';
import { buildMessageRenderPlan } from '../lib/messageRenderPlan';
import { usePlan } from '../hooks/usePlan';
import { useMemory } from '../hooks/useMemory';
import { useCanvas } from '../hooks/useCanvas';
import type { A2UISurface } from '../types/a2ui';
import { useAutoScroll } from '../hooks/useAutoScroll';
import { useUnifiedFileUpload } from '../hooks/useUnifiedFileUpload';
import { useToolApproval } from '../hooks/chat/useToolApproval';
import { PlanProgress } from './PlanProgress';
import { NewChatView } from './NewChatView';
import { ChatInputPanel } from './ChatInputPanel';
import { ImageViewer } from './ImageViewer';
import { FileViewer } from './FileViewer';
import { UserMessage, AssistantMessage, RightSidebar } from './chat';
import { useI18n } from '../i18n';
import { useHeartbeatRunning } from '../hooks/useHeartbeatRunning';
import { SubAgentView } from './sidebar/SubAgentView';
import { useSubAgentStatus } from '../hooks/useSubAgentStatus';
import { useStatusStore } from '../hooks/useStatusStore';
import type { SubAgentStatus } from './chat/SubAgentCallBlock';
import type {
  SubAgentSpawnedPayload,
  SubAgentCompletedPayload,
  SubAgentFailedPayload,
} from '../lib/streamEvents';


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
    } else if (part.type === 'a2ui' && part.surface && !part.surface.deferred) {
      // Inline A2UI surface — stored as a data attribute for re-hydration.
      // Deferred surfaces (ask_question) are transient and must not persist in history.
      const encoded = encodeURIComponent(JSON.stringify(part.surface));
      content += `\n\n<div data-a2ui="${encoded}"></div>\n\n`;
    }
  }
  return { role: 'assistant', content, timestamp: new Date().toISOString(), stepInfo: usage ? formatUsage(usage) : undefined };
}

function groupedBlocksToAssistantContent(blocks: ContentBlock[]): string {
  let content = '';
  for (const block of blocks) {
    if (block.type === 'toolCall') {
      const toolName = block.toolName || 'unknown';
      const toolCallId = block.toolCallId || '';
      const argsStr = block.toolArgs || '';
      const approvalId = block.approvalId || '';
      const stateAttr = block.approvalState === 'pending' ? 'pending' : (block.approvalState === 'denied' ? 'denied' : '');
      const attrs = ` data-tool-call-id="${toolCallId}"` +
        (approvalId ? ` data-approval-id="${approvalId}"` : '') +
        (stateAttr ? ` data-approval-state="${stateAttr}"` : '');

      content += `\n\n<details${attrs}><summary>\u{1F527} ${toolName}</summary>\n\n<pre><code class="language-text">${escapeHtmlForStore(argsStr)}</code></pre>\n\n</details>\n\n`;
      if (block.content) {
        content += `\n\n<details data-tool-call-id="${toolCallId}"><summary>\u{1F4E6} ${toolName}</summary>\n\n<pre><code class="language-text">${escapeHtmlForStore(block.content)}</code></pre>\n\n</details>\n\n`;
      }
    } else if (block.type === 'reasoning' && block.content.trim()) {
      content += `\n\n<details data-reasoning="true"><summary>Thinking</summary>\n\n${block.content}\n\n</details>\n\n`;
    }
  }
  return content;
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
      className="absolute bottom-6 right-6 z-20 w-10 h-10 bg-white dark:bg-zinc-800 text-brutal-black dark:text-white border-2 border-brutal-black dark:border-zinc-600 shadow-[4px_4px_0_0_#000] flex items-center justify-center hover:bg-neutral-100 dark:hover:bg-zinc-700 active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all animate-brutal-pop"
      title={t('chatWindow.scrollToBottom')}
    >
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
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
  streamingForCurrentChat: boolean;
  chatId?: string;
  onImageClick?: (src: string) => void;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: 'session' | null, toolName?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onInlineAction?: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
  subAgentTasks?: Record<string, { status: SubAgentStatus; resultSummary?: string; error?: string }>;
  onOpenSubAgentSidebar?: (taskId: string) => void;
  onStopSubAgent?: (taskId: string) => void;
}> = ({ messages, streamingForCurrentChat, chatId, onImageClick, onFileClick, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onInlineAction, subAgentTasks, onOpenSubAgentSidebar, onStopSubAgent }) => {
  const { skipIndices, groupRenders, stepSummaryByMessageIndex } = useMemo(
    () => buildMessageRenderPlan(messages),
    [messages],
  );

  return (
    <div className="space-y-6">
      {messages.map((m, idx) => {
        if (skipIndices.has(idx)) return null; // Part of a group, rendered by representative

        const isUser = m.role === 'user';
        const isLastMessage = idx === messages.length - 1;
        const isAssistant = !isUser;
        const group = groupRenders.get(idx);

        // Intermediate step group representative: render merged pills (no badge here — shows after final answer)
        if (group) {
          const groupedMessage: Message = {
            role: 'assistant',
            content: groupedBlocksToAssistantContent(group.mergedBlocks),
            timestamp: m.timestamp,
          };
          return (
            <div key={idx} className="chat-msg-row w-full flex flex-col group/message">
              <div className="flex justify-start w-full">
                <AssistantMessage
                  message={groupedMessage}
                  messageIndex={idx}
                  isStreaming={false}
                  isLastMessage={false}
                  onFileClick={onFileClick}
                  onToolApproval={onToolApproval}
                  toolApprovalPolicy={toolApprovalPolicy}
                  onRemoveApprovalPolicy={onRemoveApprovalPolicy}
                  onInlineAction={onInlineAction}
                  subAgentTasks={subAgentTasks}
                  onOpenSubAgentSidebar={onOpenSubAgentSidebar}
                  onStopSubAgent={onStopSubAgent}
                />
              </div>
            </div>
          );
        }

        // Regular message rendering
        const stepSummary = isAssistant ? (stepSummaryByMessageIndex.get(idx) || null) : null;

        // Canvas action message — lightweight dashed pill
        if (m.role === 'canvas_action') {
          return (
            <div key={idx} className="chat-msg-row w-full flex justify-start pl-2">
              <div className="border-2 border-dashed border-brutal-black px-4 py-2 text-sm font-mono text-neutral-500 dark:text-neutral-400 italic bg-white dark:bg-zinc-800">
                {m.content}
              </div>
            </div>
          );
        }

        return (
          <div key={idx} className="chat-msg-row w-full flex flex-col group/message">
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
                  onInlineAction={onInlineAction}
                  subAgentTasks={subAgentTasks}
                  onOpenSubAgentSidebar={onOpenSubAgentSidebar}
                  onStopSubAgent={onStopSubAgent}
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
      })}
    </div>
  );
};

// Memoised so scroll-driven setShowScrollButton re-renders in ChatWindow don't
// retrigger the O(n) message grouping logic.
const MessageListMemo = React.memo(MessageList);

interface ChatWindowProps {
  isRightSidebarOpen?: boolean;
  onRightSidebarToggle?: (isOpen: boolean) => void;
  onRightSidebarWidthChange?: (width: number | null) => void;
  rightSidebarMaxWidthPx?: number;
  viewportWidthPx?: number;
  rightSidebarForceFullView?: boolean;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  isRightSidebarOpen = false,
  onRightSidebarToggle = () => { },
  onRightSidebarWidthChange,
  rightSidebarMaxWidthPx,
  viewportWidthPx,
  rightSidebarForceFullView = false,
}) => {

  // Store hooks
  const {
    messages,
    addMessage,
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
    chats,
    refreshChatListSilently,
    updateChatTitleLocally,
  } = useChatStore();

  const { refresh: refreshPlan, applySnapshot: applyPlanSnapshot, plan } = usePlan();
  const { loadCoreMemory, loadStats } = useMemory();
  const canvas = useCanvas(currentChatId);
  const { t } = useI18n();
  const setHeartbeatRunning = useHeartbeatRunning(s => s.setRunning);

  // Local state
  const [input, setInput] = useState('');
  const [isPlanExpanded, setIsPlanExpanded] = useState(true);
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<{ path: string; name: string } | null>(null);
  const [sidebarFilePreview, setSidebarFilePreview] = useState<{ path: string; name: string } | null>(null);
  const [currentUsage, setCurrentUsage] = useState<any>(null);
  const [subAgentTasks, setSubAgentTasks] = useState<Record<string, { status: SubAgentStatus; resultSummary?: string; error?: string }>>({});
  const [viewingSubAgentTaskId, setViewingSubAgentTaskId] = useState<string | null>(null);
  const { onSpawned: onSubAgentSpawned, onCompleted: onSubAgentCompleted, onFailed: onSubAgentFailed } = useSubAgentStatus();
  const { setStatus: setStatusBar } = useStatusStore();
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
  // Set to true while a live background stream is active — onFinish should skip addMessage/forceSaveNow.
  const isLiveStreamRef = useRef(false);
  // Captures the final AGUI parts from a live background stream so the cleanup path can
  // convert them to a persisted rich message (with tool-step HTML) after clearParts.
  const liveStreamPartsRef = useRef<AGUIPart[]>([]);

  // ── AG-UI streaming hook ─────────────────────────────────────────────
  const {
    parts: streamingParts,
    sendMessage: sendAGUI,
    resumeStream,
    steerStream,
    stop: stopAGUIStream,
    clearParts,
    resolveApproval,
    addApprovalDecision,
    consumeApprovalDecisions,
    removeInlineSurface,
  } = useAGUI({
    url: `${getApiBase()}/chat`,
    onFinish: (parts) => {
      const chatId = streamingChatIdRef.current || activeChatIdRef.current;

      const hasPendingApprovals = parts.some(
        p => p.type === 'tool' && p.state === 'approval-requested'
      );

      if (heartbeatOkRef.current) {
        // HEARTBEAT_OK: backend rolled back the messages; discard streamed content and reload.
        setHeartbeatRunning(false, null);
        heartbeatInFlightRef.current = false;
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
        }
        heartbeatInFlightRef.current = false;
        setCurrentUsage(null);
        // For live background streams (social/cron), save the parts so tryConnect's
        // cleanup can detect the pending-approval state and skip clearParts().
        if (isLiveStreamRef.current) {
          liveStreamPartsRef.current = parts;
        }
        return;
      }

      if (isLiveStreamRef.current) {
        // Live background stream: backend already persisted the message.
        // Capture final parts so the cleanup path can persist the rich (tool-step) version.
        // Do NOT call addMessage, forceSaveNow, setIsStreaming(false), or clearParts here.
        // The live stream effect's finally() handles all cleanup AFTER loadChat resolves,
        // so streaming parts stay visible until the DB reload completes — no blank flash.
        liveStreamPartsRef.current = parts;
        streamingChatIdRef.current = null;
        setCurrentUsage(null);
        return;
      }

      // 100% Backend Authored: instead of pushing frontend-assembled HTML,
      // load the official JSON-based chat history from the backend.
      if (heartbeatInFlightRef.current) {
        setHeartbeatRunning(false, null);
      }
      heartbeatInFlightRef.current = false;
      streamingChatIdRef.current = null;
      // Clear any stale live-stream parts from a previous background turn so
      // tryConnect's cleanup path doesn't convert them to a redundant message.
      liveStreamPartsRef.current = [];

      // Optimistic append: convert parts to HTML and store locally so the
      // message is visible immediately — no blank flash while loadChat fetches DB.
      const storeMsg = aguiPartsToStoreMessage(parts, currentUsage);
      if (storeMsg.content.trim()) {
        addMessage(storeMsg, chatId!);
      }

      setCurrentUsage(null);
      // Clear streaming state synchronously in the same React batch as addMessage so
      // the transient assistant bubble is replaced by the optimistic message in one
      // render. Previously these lived in .finally(), causing a window where the
      // transient disappeared but the DB reload hadn't returned yet — the user saw
      // stale pending-approval tool blocks from the backend race condition.
      setIsStreaming(false, chatId);
      clearParts();

      // Background DB sync — delay slightly so the backend has time to commit tool
      // results before we reload. An immediate reload risks getting stale
      // approval-requested state that the guards may not catch in all edge cases.
      const _syncChatId = chatId!;
      setTimeout(() => { try { loadChat(_syncChatId); } catch { } }, 800);

      try { loadCoreMemory(); loadStats(); } catch { }
    },
    onMarkDeferred: (surfaceId) => {
      canvas.markDeferred(surfaceId);
    },
    onCustomEvent: (name, value) => {
      if (name === 'chat_title_updated') {
        const { chat_id: titleChatId, title } = value as { chat_id: string; title: string };
        if (titleChatId && title) updateChatTitleLocally(titleChatId, title);
        return;
      } else if (name === 'plan_refresh') {
        const chatId = streamingChatIdRef.current || activeChatIdRef.current;
        applyPlanSnapshot(value as any);
        refreshPlan(chatId);
      } else if (name === 'usage_update') {
        setCurrentUsage(value);
      } else if (name === 'heartbeat_ok') {
        // Backend signals that this heartbeat run was OK and messages were rolled back.
        heartbeatOkRef.current = true;
      } else if (name === 'subagent_spawned') {
        const p = value as SubAgentSpawnedPayload;
        onSubAgentSpawned(p);
        setSubAgentTasks(prev => ({ ...prev, [p.task_id]: { status: 'running' } }));
      } else if (name === 'subagent_completed') {
        const p = value as SubAgentCompletedPayload;
        onSubAgentCompleted(p);
        setSubAgentTasks(prev => ({ ...prev, [p.task_id]: { status: 'completed', resultSummary: p.result_summary } }));
        setStatusBar(`Sub-agent completed — ${p.task_id}`, 'success', 5000);
      } else if (name === 'subagent_failed') {
        const p = value as SubAgentFailedPayload;
        onSubAgentFailed(p);
        setSubAgentTasks(prev => ({ ...prev, [p.task_id]: { status: 'failed', error: p.error } }));
        setStatusBar(`Sub-agent failed — ${p.task_id}`, 'error', 5000);
      } else if (name === 'a2ui.render') {
        const rawSurface = value as (A2UISurface & { chatId?: string }) | null;
        if (!rawSurface || typeof rawSurface !== 'object' || !('id' in rawSurface) || !('component' in rawSurface)) {
          return;
        }
        const sourceChatId = rawSurface.chatId || streamingChatIdRef.current || activeStreamingChatId || null;
        const viewedChatId = activeChatIdRef.current;
        if (sourceChatId && viewedChatId && sourceChatId !== viewedChatId) {
          return;
        }
        const { chatId: _eventChatId, ...surfaceData } = rawSurface;
        const surface = surfaceData as A2UISurface;
        const isFirst = !canvas.hasSurfaces;
        canvas.setSurface(surface);
        if (isFirst) {
          onRightSidebarToggle(true);
        }
      }
    },
    onError: (error) => {
      console.error('AG-UI error:', error);
      const chatId = streamingChatIdRef.current || activeChatIdRef.current;
      const wasHeartbeat = heartbeatInFlightRef.current;
      if (wasHeartbeat) setHeartbeatRunning(false, null);
      heartbeatInFlightRef.current = false;
      heartbeatOkRef.current = false;
      setIsStreaming(false, chatId);
      streamingChatIdRef.current = null;
      stopInFlightRef.current = false;
      const errorMessage = typeof error?.message === 'string' ? error.message : '';
      const isNetworkError = errorMessage === 'Failed to fetch' || error instanceof TypeError;
      const isOutputValidationRetryError =
        errorMessage.includes('output validation') &&
        errorMessage.includes('Exceeded maximum retries');

      const displayMessage = isOutputValidationRetryError
        ? t('chatWindow.outputValidationRetryError')
        : (errorMessage || t('chatWindow.genericError'));

      if (!wasHeartbeat && !isLiveStreamRef.current && !isNetworkError) {
        addMessage({ role: 'assistant', content: `\u26a0\ufe0f Error: ${displayMessage}` }, chatId);
      }
      isLiveStreamRef.current = false;
      liveStreamPartsRef.current = [];
    },
  });

  // Listen for external message triggers (e.g. from Heartbeat "Run Now")
  useEffect(() => {
    const handler = (e: any) => {
      const { body, options } = e.detail || {};
      const isHeartbeat = Boolean(body?.is_heartbeat);
      heartbeatInFlightRef.current = isHeartbeat;
      if (body) {
        const chatId = body.chat_id || currentChatId;
        if (isHeartbeat) setHeartbeatRunning(true, chatId);
        sendAGUI(body, options).catch(err => {
          heartbeatInFlightRef.current = false;
          if (isHeartbeat) setHeartbeatRunning(false, null);
          console.error('[ChatWindow] External sendAGUI failed:', err);
        });
      }
    };
    window.addEventListener('agui:send-message', handler);
    return () => window.removeEventListener('agui:send-message', handler);
  }, [sendAGUI, currentChatId, setHeartbeatRunning]);

  const { handleToolApproval } = useToolApproval({
    currentChatId,
    activeStreamingChatId,
    config,
    messages,
    streamingParts,
    streamingChatIdRef,
    activeChatIdRef,
    stopInFlightRef,
    setConfig,
    updateMessage,
    setIsStreaming,
    resumeStream,
    resolveApproval,
    addApprovalDecision,
    consumeApprovalDecisions,
  });

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

  // handleCanvasDispatch is defined after safeConfig below

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
  const _prefs = backendConfig?.userPreferences;
  const _base = config || { model: '', agent: '', tools: [] as string[] };
  // Platform chats (cron, social) have no model/agent — fall back to user prefs.
  // The config selector is hidden for these chats so users can't override the managed config.
  const _isPlatformChat = !!(config as any)?.platform;
  const safeConfig = {
    ..._base,
    model: _base.model || (_isPlatformChat ? (_prefs?.model || backendConfig?.models?.[0] || '') : ''),
    agent: _base.agent || (_isPlatformChat ? (_prefs?.agent || backendConfig?.agents?.[0] || '') : ''),
    tools: _base.tools?.length ? _base.tools : (_isPlatformChat ? (_prefs?.tools ?? []) : []),
  };

  // Unified canvas action dispatcher — used by both the canvas sidebar panel and inline surfaces.
  // Adds a decorative canvas_action pill to the chat, then starts a real AG-UI stream so the
  // agent's reply appears with full streaming (tool calls, typewriter, etc.).
  const handleCanvasDispatch = useCallback(async (
    action: string,
    context: Record<string, unknown>,
    surfaceId: string,
  ) => {
    if (!currentChatId) return;

    // Deferred surface (ask_question): resolve the waiting tool call directly,
    // no new agent turn needed — the existing stream will continue.
    if (canvas.deferredIds.has(surfaceId)) {
      const answer = { ...context };
      delete answer.button_label;
      // If it was a button click, use the label as the answer value
      if (context.button_label) answer.answer = context.button_label;
      // Remove the form immediately — the tool is done, no need to keep it visible
      removeInlineSurface(surfaceId);
      try {
        await fetch(`${getApiBase()}/canvas/${currentChatId}/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ surface_id: surfaceId, answer }),
        });
      } catch (err) {
        console.error('[A2UI] answer dispatch failed:', err);
      }
      return;
    }

    // Regular canvas action: add a pill message and start a new agent stream.
    const buttonLabel = context.button_label as string | undefined;
    const ctxRest = { ...context };
    delete ctxRest.button_label;
    if (surfaceId && !('surface_id' in ctxRest)) {
      ctxRest.surface_id = surfaceId;
    }
    const labelStr = buttonLabel ? ` "${buttonLabel}"` : '';
    const contextStr = Object.keys(ctxRest).length > 0 ? ` ${JSON.stringify(ctxRest)}` : '';
    const messageContent = `[canvas: ${action}]${labelStr}${contextStr}`;

    addMessage(
      { role: 'canvas_action', content: messageContent, timestamp: new Date().toISOString() },
      currentChatId,
    );

    setIsStreaming(true, currentChatId);
    streamingChatIdRef.current = currentChatId;
    activeChatIdRef.current = currentChatId;
    stopInFlightRef.current = false;

    try {
      await sendAGUI({ message: messageContent, config: safeConfig, chat_id: currentChatId });
    } catch (err) {
      console.error('[A2UI] canvas dispatch failed:', err);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentChatId, canvas.deferredIds, addMessage, setIsStreaming, sendAGUI]);


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

  const handleOpenSubAgentSidebar = useCallback((taskId: string) => {
    setViewingSubAgentTaskId(taskId);
    onRightSidebarToggle(true);
  }, [onRightSidebarToggle]);

  const handleStopSubAgent = useCallback(async (taskId: string) => {
    try {
      await fetch(`${getApiBase()}/subagents/${taskId}/stop`, { method: 'POST' });
    } catch { /* ignore */ }
  }, []);


  // Auto-scroll
  const { scrollContainerRef, bottomRef, showScrollButton, scrollToBottom } = useAutoScroll(
    [safeMessages, isStreaming, isRightSidebarOpen, isPlanExpanded, canvas?.hasSurfaces]
  );

  // Refresh plan when chat changes
  useEffect(() => {
    refreshPlan(currentChatId);
  }, [currentChatId, refreshPlan]);

  // Live background stream: when a background platform chat (cron/heartbeat/social) is open,
  // poll /chat/live/{chat_id} on a tight 2s interval. As soon as a stream is active (non-204),
  // subscribe and render events live. This avoids the 5s chat-list poll delay that would
  // otherwise cause late joins or missed fast streams.
  const currentChatSummary = chats.find(c => c.id === currentChatId);
  const isBackgroundChat = !!currentChatSummary?.platform || !!currentChatSummary?.heartbeatEnabled;
  useEffect(() => {
    if (!currentChatId || !isBackgroundChat) return;

    let cancelled = false;

    // On re-entry: reload from DB so any stream that completed while away is visible.
    loadChat(currentChatId).catch(() => {});

    const tryConnect = async (): Promise<boolean> => {
      if (isLiveStreamRef.current) return false; // already streaming
      // Don't probe while a user-initiated stream is active — it shares the same
      // AbortController ref and probing would overwrite the real stream's controller.
      // Use the ref (not the closed-over state) so this is never stale.
      if (streamingChatIdRef.current === currentChatId) return false;
      const liveUrl = `${getApiBase()}/chat/live`;
      const chatIdAtStart = currentChatId;

      // Single fetch: connectToLiveStream handles 204 (no stream) returning false,
      // or streams and returns true. onStreamStart fires only when a real stream is found.
      const streamed = await sendAGUI({ chat_id: currentChatId }, {
        urlOverride: liveUrl,
        onStreamStart: () => {
          isLiveStreamRef.current = true;
          // Pin the streaming chat ID so onFinish uses the correct chat even if
          // the user navigates away (causing activeChatIdRef to point elsewhere).
          streamingChatIdRef.current = chatIdAtStart;
          setIsStreaming(true, chatIdAtStart);
          // Reload messages now that the stream has confirmed active: the backend
          // pre-saves the user message to DB before yielding the first SSE event,
          // so this loadChat will pick it up and show it alongside the stream.
          loadChat(chatIdAtStart).catch(() => {});
        },
      });

      if (!streamed || cancelled) return false;

      // If the stream paused for tool approval, onFinish saved the parts to
      // liveStreamPartsRef. Keep the approval UI visible and let the 2-second
      // poll re-subscribe when the resume stream starts; don't clearParts.
      const pendingApproval = liveStreamPartsRef.current.some(
        p => p.type === 'tool' && p.state === 'approval-requested'
      );
      if (pendingApproval) {
        isLiveStreamRef.current = false;
        liveStreamPartsRef.current = [];
        return true;
      }

      // Convert the captured streaming parts to a rich message (includes tool-step HTML).
      // This must happen before clearParts so the parts are still populated.
      const richMsg = aguiPartsToStoreMessage(liveStreamPartsRef.current, null);

      const isSocialStream = chatIdAtStart.startsWith('social-');

      // Stop streaming indicator before any async work so transient parts stop
      // rendering while we wait for the DB reload.
      setIsStreaming(false, chatIdAtStart);

      if (isSocialStream) {
        // Social chats: backend rebuilds the full message log asynchronously after the
        // stream, so loadChat may return stale (pre-rebuild) data if called immediately.
        // Add the optimistic rich message first — the loadChat length guard will then
        // block any stale DB state from overwriting it, preventing a blank flash.
        if (richMsg.content.trim()) {
          addMessage(richMsg, chatIdAtStart);
        }
        try { await loadChat(chatIdAtStart); } catch { /* ignore */ }
      }

      clearParts();
      liveStreamPartsRef.current = [];
      isLiveStreamRef.current = false;

      // Desktop/heartbeat/cron: add the rich message (tool-step HTML) to the store.
      // addMessage schedules an 800ms autosave, which is faster than the 5-s polling
      // loadChat, so the store guard (existing.length >= serverMessages.length) will
      // preserve the rich message through polling reloads until the autosave fires.
      if (!isSocialStream && richMsg.content.trim()) {
        addMessage(richMsg, chatIdAtStart);
      }

      return true;
    };

    let probeDelayMs = 2000;
    let timer: NodeJS.Timeout | null = null;

    const scheduleProbe = (delayMs: number) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(async () => {
        if (cancelled) return;

        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
          probeDelayMs = Math.min(Math.max(probeDelayMs, 8000), 15000);
          scheduleProbe(probeDelayMs);
          return;
        }

        const connected = await tryConnect();
        probeDelayMs = connected ? 2000 : Math.min(probeDelayMs + 1500, 10000);
        scheduleProbe(probeDelayMs);
      }, delayMs);
    };

    // Probe immediately, then adaptively back off while idle.
    scheduleProbe(0);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      stopAGUIStream();
      isLiveStreamRef.current = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentChatId, isBackgroundChat]);

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

    // If currently streaming (or paused on pending approvals) for this chat,
    // steer instead of starting a brand-new turn.
    if ((streamingForCurrentChat || hasPendingTransientApprovals) && currentChatId) {
      setInput('');
      addMessage({ role: 'user', content: prompt, timestamp: new Date().toISOString() }, currentChatId);

      steeringRef.current = true;
      setIsStreaming(true, currentChatId);
      streamingChatIdRef.current = currentChatId;
      activeChatIdRef.current = currentChatId;
      stopInFlightRef.current = false;
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
      images: uploadedFileMetadata ? undefined : imagePreviews,
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
  const handleFileClick = useCallback(async (path: string, name: string, shiftKey?: boolean) => {
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
  }, [currentChatId, config.sandbox_volumes, isRightSidebarOpen, onRightSidebarToggle]);

  const handleInlineAction = useCallback((surfaceId: string, action: string, context: Record<string, unknown>) => {
    handleCanvasDispatch(action, context, surfaceId);
  }, [handleCanvasDispatch]);

  // Handle maximize button from sidebar
  const handleMaximizeFile = (path: string, name: string) => {
    setViewingFile({ path, name });
  };

  return (
    <div
      className="flex flex-row flex-1 h-full min-h-0 overflow-x-hidden bg-neutral-50 dark:bg-zinc-900 relative"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {isDragging && <DragOverlay />}

      {/* Main Chat Column */}
      <div className="flex flex-col flex-1 min-w-0 min-h-0 h-full relative">
        <div className="absolute top-2 right-6 z-10 pointer-events-none flex flex-col items-end gap-1">
          {currentUsage && safeBackendConfig?.maxContextTokens && (
            <div className="flex items-center gap-1.5 text-[10px] text-neutral-500 dark:text-neutral-400 pointer-events-none">
              <div className="w-16 h-1.5 rounded-full bg-neutral-200 dark:bg-zinc-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-neutral-500 dark:bg-neutral-400 transition-all"
                  style={{ width: `${Math.min(100, ((currentUsage.total_tokens ?? currentUsage.total ?? 0) / safeBackendConfig.maxContextTokens) * 100)}%` }}
                />
              </div>
              <span>{((currentUsage.total_tokens ?? currentUsage.total ?? 0) / 1000).toFixed(0)}k / {(safeBackendConfig.maxContextTokens / 1000).toFixed(0)}k</span>
            </div>
          )}
        </div>

        <div className="relative flex-1 min-h-0">
          <div
            ref={scrollContainerRef}
            className={safeMessages.length === 0
              ? "h-full overflow-hidden p-4 md:p-6 pb-2 bg-neutral-50 dark:bg-zinc-900"
              : "h-full overflow-y-auto overflow-x-hidden px-4 md:px-6 pt-3 pb-6 scrollbar-thin bg-neutral-50 dark:bg-zinc-900"
            }
          >
            {safeMessages.length === 0 && !showTransientAssistant ? (
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
                {safeMessages.length > 0 && (
                  <MessageListMemo
                    messages={safeMessages}
                    streamingForCurrentChat={false}
                    chatId={currentChatId ?? undefined}
                    onImageClick={setViewingImage}
                    onFileClick={handleFileClick}
                    onToolApproval={handleToolApproval}
                    toolApprovalPolicy={safeConfig.tool_approval_policy}
                    onRemoveApprovalPolicy={handleRemoveApprovalPolicy}
                    onInlineAction={handleInlineAction}
                    subAgentTasks={subAgentTasks}
                    onOpenSubAgentSidebar={handleOpenSubAgentSidebar}
                    onStopSubAgent={handleStopSubAgent}
                  />
                )}
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
                          onInlineAction={handleInlineAction}
                          subAgentTasks={subAgentTasks}
                          onOpenSubAgentSidebar={handleOpenSubAgentSidebar}
                          onStopSubAgent={handleStopSubAgent}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

            {!configReady && <LoadingIndicator />}
            <div ref={bottomRef} className="h-0" />
          </div>

          {showScrollButton && <ScrollToBottomButton onClick={scrollToBottom} />}
        </div>

        {/* Input Panel (shown when messages exist) */}
        {safeMessages.length > 0 && (
          <div className="p-4 flex flex-col gap-3 bg-neutral-50 dark:bg-zinc-900 relative z-10 shrink-0">
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
              hideConfigSelector={_isPlatformChat}
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
        onOpen={() => onRightSidebarToggle(true)}
        onWidthChange={onRightSidebarWidthChange}
        maxWidthPx={rightSidebarMaxWidthPx}
        viewportWidthPx={viewportWidthPx}
        forceFullView={rightSidebarForceFullView}
        plan={plan}
        isPlanExpanded={isPlanExpanded}
        onTogglePlanExpand={() => setIsPlanExpanded(!isPlanExpanded)}
        fileToPreview={sidebarFilePreview}
        onMaximizeFile={handleMaximizeFile}
        canvas={canvas}
        onCanvasDispatch={handleCanvasDispatch}
        viewingSubAgentTaskId={viewingSubAgentTaskId}
        onCloseSubAgent={() => setViewingSubAgentTaskId(null)}
        onSelectSubAgent={(taskId) => setViewingSubAgentTaskId(taskId)}
        currentChatId={currentChatId}
        hasSubAgents={Object.keys(subAgentTasks).length > 0}
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
