import { useCallback, useRef, type MutableRefObject } from 'react';
import { stripDenyApprovalPolicies } from '../../lib/approvalPolicy';
import type { ChatConfig, Message } from '../../types/api';
import type { AGUIPart, ApprovalRememberScope } from '../useAGUI';

interface ToolApprovalDecision {
  approvalId: string;
  toolCallId: string;
  approved: boolean;
  remember?: ApprovalRememberScope;
  toolName?: string;
  args?: Record<string, unknown> | null;
  actionId?: string;
  feedback?: string;
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
    remember?: ApprovalRememberScope,
    toolName?: string,
    args?: Record<string, unknown> | null,
    actionId?: string,
    feedback?: string,
  ) => boolean;
  consumeApprovalDecisions: () => ToolApprovalDecision[];
}

interface UseToolApprovalReturn {
  handleToolApproval: (
    approvalId: string,
    toolCallId: string,
    approved: boolean,
    remember?: ApprovalRememberScope,
    toolName?: string,
    actionId?: string,
    feedback?: string,
  ) => Promise<void>;
}

function parseToolArgs(rawArgs: string | undefined): Record<string, unknown> | null {
  if (!rawArgs) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawArgs);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function normalizeLegacyRememberScope(scope: ApprovalRememberScope | 'project' | undefined): ApprovalRememberScope {
  if (scope === 'project') {
    return 'global';
  }
  return scope ?? null;
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
    remember?: ApprovalRememberScope,
    toolName?: string,
    actionId?: string,
    feedback?: string,
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

    const matchingPart = streamingPartsRef.current.find(
      p => p.type === 'tool' && p.toolCallId === toolCallId,
    );
    const toolArgs = parseToolArgs(matchingPart?.args);

    const effectiveRemember = normalizeLegacyRememberScope(remember);

    let allDecided = addApprovalDecision(
      approvalId,
      toolCallId,
      approved,
      effectiveRemember,
      toolName,
      toolArgs,
      actionId,
      feedback,
    );

    if (!allDecided) return;

    const decisions = consumeApprovalDecisions();
    const currentConfig = config || { model: '', agent: '', tools: [] };

    const resumeApprovals = decisions.map(d => ({
      request_id: d.approvalId,
      tool_call_id: d.toolCallId,
      approved: d.approved,
      remember: d.remember,
      tool_name: d.toolName,
      args: d.args,
      action_id: d.actionId,
      feedback: d.feedback,
    }));

    try {
      const payload: Record<string, unknown> = {
        message: '',
        config: stripDenyApprovalPolicies(currentConfig),
        chat_id: targetChatId,
        reset: false,
        resume_approvals: resumeApprovals,
      };

      setIsStreaming(true, targetChatId);
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
    setIsStreaming,
    stopInFlightRef,
    resumeStream,
  ]);

  return { handleToolApproval };
}
