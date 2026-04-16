import { useCallback, useRef, type MutableRefObject } from 'react';
import type { ChatConfig, Message } from '../../types/api';
import type { AGUIPart, ApprovalRememberScope } from '../useAGUI';

interface ToolApprovalDecision {
  approvalId: string;
  toolCallId: string;
  approved: boolean;
  remember?: ApprovalRememberScope;
  toolName?: string;
  args?: Record<string, unknown> | null;
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
    remember?: ApprovalRememberScope,
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

    const matchingPart = streamingPartsRef.current.find(
      p => p.type === 'tool' && p.toolCallId === toolCallId,
    );
    const toolArgs = parseToolArgs(matchingPart?.args);

    const effectiveRemember = toolName === 'bash_execute' ? normalizeLegacyRememberScope(remember) : null;

    let allDecided = addApprovalDecision(
      approvalId,
      toolCallId,
      approved,
      effectiveRemember,
      toolName,
      toolArgs,
    );

    if ((effectiveRemember === 'session' || effectiveRemember === 'global') && toolName) {
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
        .map(p => ({
          approvalId: p.approvalId as string,
          toolCallId: p.toolCallId as string,
          args: parseToolArgs(p.args),
        }));

      for (const linked of linkedPending) {
        resolveApproval(linked.approvalId, approved);
        updateApprovalStateInHistory(linked.approvalId, newState);
        allDecided =
          addApprovalDecision(linked.approvalId, linked.toolCallId, approved, null, toolName, linked.args) ||
          allDecided;
      }
    }

    if (!allDecided) return;

    const decisions = consumeApprovalDecisions();

    let currentConfig = config || { model: '', agent: '', tools: [] };
    let hasPolicyUpdate = false;
    const policyUpdates: Record<string, string> = {};

    decisions.forEach(d => {
    });

    const mergedPermissionPolicies: Record<string, any> = {
      ...(currentConfig.permission_policies || {}),
    };
    let hasPermissionPolicyUpdate = false;

    decisions.forEach(d => {
      if ((d.remember === 'session' || d.remember === 'global') && d.toolName === 'bash_execute') {
        const command = typeof d.args?.command === 'string' ? d.args.command.trim() : '';
        if (!command) {
          return;
        }

        const existing = mergedPermissionPolicies.bash_execute || {};
        const existingRules = Array.isArray(existing.command_rules)
          ? existing.command_rules.filter((r: any) => r && typeof r === 'object')
          : [];

        const nextRule = {
          pattern: command,
          match_type: 'exact',
          action: d.approved ? 'allow' : 'deny',
        };

        const sameIndex = existingRules.findIndex((r: any) => {
          return (
            String(r.pattern || '').trim() === nextRule.pattern &&
            String(r.match_type || '').trim().toLowerCase() === nextRule.match_type
          );
        });

        if (sameIndex >= 0) {
          existingRules[sameIndex] = nextRule;
        } else {
          existingRules.push(nextRule);
        }

        mergedPermissionPolicies.bash_execute = {
          enabled: true,
          mode: existing.mode || 'accept_edits',
          default_action: existing.default_action || 'ask',
          ...existing,
          command_rules: existingRules,
        };
        hasPermissionPolicyUpdate = true;
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

    if (hasPermissionPolicyUpdate) {
      currentConfig = {
        ...currentConfig,
        permission_policies: mergedPermissionPolicies,
      };
      setConfig(currentConfig);
    }

    const resumeApprovals = decisions.map(d => ({
      request_id: d.approvalId,
      tool_call_id: d.toolCallId,
      approved: d.approved,
      remember: d.remember,
      tool_name: d.toolName,
      args: d.args,
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
