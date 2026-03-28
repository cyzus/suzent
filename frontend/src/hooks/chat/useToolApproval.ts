import { useCallback, useRef, type MutableRefObject } from 'react';
import type { ChatConfig, Message } from '../../types/api';
import type { AGUIPart } from '../useAGUI';

interface ToolApprovalDecision {
  approvalId: string;
  toolCallId: string;
  approved: boolean;
  remember?: 'session' | null;
  toolName?: string;
}

interface UseToolApprovalOptions {
  currentChatId: string | null;
  activeStreamingChatId: string | null;
  config: ChatConfig;
  messages: Message[];
  streamingParts: AGUIPart[];
  streamingChatIdRef: MutableRefObject<string | null>;
  activeChatIdRef: MutableRefObject<string | null>;
  stopInFlightRef: MutableRefObject<boolean>;
  setConfig: (c: ChatConfig | ((prev: ChatConfig) => ChatConfig)) => void;
  updateMessage: (index: number, update: Partial<Message>, chatId?: string | null) => void;
  setIsStreaming: (streaming: boolean, chatId?: string | null) => void;
  resumeStream: (body: Record<string, unknown>) => Promise<void>;
  resolveApproval: (approvalId: string, approved: boolean) => void;
  addApprovalDecision: (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: 'session' | null,
    toolName?: string,
  ) => boolean;
  consumeApprovalDecisions: () => ToolApprovalDecision[];
}

interface UseToolApprovalReturn {
  handleToolApproval: (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: 'session' | null,
    toolName?: string,
  ) => Promise<void>;
}

export function useToolApproval(options: UseToolApprovalOptions): UseToolApprovalReturn {
  const {
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
  } = options;

  // Keep refs so the callback never needs to re-create just because messages/parts changed.
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const streamingPartsRef = useRef(streamingParts);
  streamingPartsRef.current = streamingParts;

  const handleToolApproval = useCallback(async (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: 'session' | null,
    toolName?: string,
  ) => {
    const targetChatId =
      streamingChatIdRef.current ||
      activeStreamingChatId ||
      activeChatIdRef.current ||
      currentChatId;

    if (!targetChatId) return;

    const updateApprovalStateInHistory = (id: string, state: 'approved' | 'denied') => {
      messagesRef.current.forEach((m, idx) => {
        if (m.role === 'assistant' && m.content.includes(`data-approval-id="${id}"`)) {
          const finalContent = m.content.replace(
            new RegExp(`(<details[^>]*data-approval-id="${id}"[^>]*data-approval-state=")pending(")`),
            `$1${state}$2`,
          );

          if (finalContent !== m.content) {
            updateMessage(idx, { content: finalContent }, targetChatId);
          }
        }
      });
    };

    resolveApproval(approvalId, approved);

    const newState = approved ? 'approved' : 'denied';
    updateApprovalStateInHistory(approvalId, newState);

    let allDecided = addApprovalDecision(approvalId, toolCallId, approved, remember, toolName);

    if (remember === 'session' && toolName) {
      const linkedPending = streamingPartsRef.current
        .filter(
          p =>
            p.type === 'tool' &&
            p.state === 'approval-requested' &&
            p.toolName === toolName &&
            p.approvalId &&
            p.approvalId !== approvalId &&
            p.toolCallId,
        )
        .map(p => ({ approvalId: p.approvalId as string, toolCallId: p.toolCallId as string }));

      for (const linked of linkedPending) {
        resolveApproval(linked.approvalId, approved);
        updateApprovalStateInHistory(linked.approvalId, newState);
        allDecided =
          addApprovalDecision(linked.approvalId, linked.toolCallId, approved, null, toolName) ||
          allDecided;
      }
    }

    if (!allDecided) return;

    const decisions = consumeApprovalDecisions();

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
          ...policyUpdates,
        },
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
        message: '',
        config: currentConfig,
        chat_id: targetChatId,
        reset: false,
        resume_approvals: resumeApprovals,
      };

      setIsStreaming(true, targetChatId);
      streamingChatIdRef.current = targetChatId;
      stopInFlightRef.current = false;
      await resumeStream(payload);
    } catch (error) {
      console.error('Failed to resume with tool approval:', error);
      setIsStreaming(false, targetChatId);
      stopInFlightRef.current = false;
    }
  }, [
    streamingChatIdRef,
    activeStreamingChatId,
    activeChatIdRef,
    currentChatId,
    updateMessage,
    resolveApproval,
    addApprovalDecision,
    consumeApprovalDecisions,
    config,
    setConfig,
    setIsStreaming,
    stopInFlightRef,
    resumeStream,
  ]);

  return { handleToolApproval };
}
