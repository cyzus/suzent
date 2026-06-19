import { useCallback, type MutableRefObject } from 'react';
import type { AGUIPart } from '../useAGUI';
import type { PendingPermissionApproval } from '../../lib/api';

/**
 * Restores a suspended-for-approval run's transient UI when a chat is re-entered.
 *
 * Why this exists
 * ---------------
 * When the agent pauses on a tool approval, its turn generator has already
 * finished — there is no live `/chat/live` stream to reconnect to (that endpoint
 * returns 204 once the background queue is gone). The live approval request,
 * including its `approvalId`, lives ONLY in the streaming parts. We snapshot
 * those parts to sessionStorage on navigate-away so that, on return, we can
 * re-hydrate the approval dialog with an actionable `approvalId`.
 *
 * The persisted DB message is NOT a substitute: a reloaded `approval-requested`
 * tool part carries no `approvalId`, so AssistantMessage renders it as denied/
 * skipped, not pending (see `isActionablyPending`). The seed is the only carrier
 * of the live approval handle across a chat switch.
 *
 * The bug this fixes
 * ------------------
 * The previous implementation armed a 5s self-destruct timer after restoring,
 * keyed on `!isLiveStreamRef.current`, on the assumption that "no live stream
 * within 5s ⇒ backend already finished". But a suspended approval run is exactly
 * the case where there is legitimately no live stream — so the timer always
 * fired, wiping a valid pending approval after 5s. Once the UI lost its buttons,
 * the next reload/steer treated the unanswered tool call as cancelled and the
 * backend auto-denied it.
 *
 * A pending approval must persist as pending until the user acts. So we restore
 * and hold the UI open with no timer. It is cleared only when the user
 * approves/denies, or when a subsequent DB reload proves the approval was already
 * resolved (the tool now has output) — handled by the normal reload guards.
 */
export interface UseApprovalRestoreOptions {
  restorePartsFromSeed: (seed: AGUIPart[]) => void;
  setIsStreaming: (streaming: boolean, chatId?: string | null) => void;
  clearParts: () => void;
  streamingChatIdRef: MutableRefObject<string | null>;
}

export interface UseApprovalRestoreReturn {
  /**
   * Attempt to restore pending-approval UI from a saved seed for `chatId`.
   * Returns true if a pending approval was restored (so the caller can skip
   * faking a live-stream state). No-op + false when the seed has no actionable
   * pending approvals.
   */
  restorePendingApprovals: (chatId: string, seedParts: AGUIPart[]) => boolean;
  /**
   * Tear down restored approval UI for `chatId` once the persisted DB state
   * proves every restored approval was already resolved (e.g. approved/denied
   * in another window while we were away). `resolvedToolCallIds` are tool-call
   * IDs that now carry an output / non-pending state in the reloaded messages.
   * Clears only when NONE of the restored pending tool calls is still
   * outstanding. This is the only path that clears restored pending state
   * besides the user acting on it — replacing the old blind 5s timer that wiped
   * valid pending approvals.
   */
  clearIfResolved: (
    chatId: string,
    transientParts: AGUIPart[],
    resolvedToolCallIds: Set<string>,
  ) => void;
}

function seedHasPendingApprovals(parts: AGUIPart[]): boolean {
  return parts.some(
    p => p.type === 'tool' && p.state === 'approval-requested' && !!p.approvalId,
  );
}

export function permissionApprovalsToParts(
  approvals: PendingPermissionApproval[],
): AGUIPart[] {
  return approvals.flatMap(approval => {
    if (!approval.approvalId || !approval.toolCallId || !approval.decision) {
      return [];
    }
    return [{
      type: 'tool' as const,
      toolCallId: approval.toolCallId,
      toolName: approval.toolName || 'unknown',
      args: JSON.stringify(approval.args || {}, null, 2),
      state: 'approval-requested' as const,
      approvalId: approval.approvalId,
      permission: approval.decision,
    }];
  });
}

export function useApprovalRestore(
  options: UseApprovalRestoreOptions,
): UseApprovalRestoreReturn {
  const { restorePartsFromSeed, setIsStreaming, clearParts, streamingChatIdRef } =
    options;

  const restorePendingApprovals = useCallback(
    (chatId: string, seedParts: AGUIPart[]): boolean => {
      if (!seedHasPendingApprovals(seedParts)) {
        return false;
      }

      // Re-hydrate the approval dialog with its live `approvalId` and keep the
      // chat in a streaming state so the approve/deny buttons stay actionable
      // (AssistantMessage gates buttons on `isStreaming`). Deliberately NO
      // self-destruct timer: the pending approval persists until the user acts
      // or a reload proves it resolved. The backend keeps the run suspended.
      restorePartsFromSeed(seedParts);
      setIsStreaming(true, chatId);
      streamingChatIdRef.current = chatId;
      return true;
    },
    [restorePartsFromSeed, setIsStreaming, streamingChatIdRef],
  );

  const clearIfResolved = useCallback(
    (
      chatId: string,
      transientParts: AGUIPart[],
      resolvedToolCallIds: Set<string>,
    ): void => {
      // Only act while we hold restored transient state for this chat.
      if (streamingChatIdRef.current !== chatId) {
        return;
      }
      const restoredPending = transientParts.filter(
        p => p.type === 'tool' && p.state === 'approval-requested' && !!p.approvalId,
      );
      if (restoredPending.length === 0) {
        return;
      }
      // Keep the UI up as long as ANY restored approval is still outstanding in
      // the DB. Only when every restored approval is resolved server-side do we
      // tear down — so a genuinely-pending approval never gets cleared.
      const stillOutstanding = restoredPending.some(
        p => !p.toolCallId || !resolvedToolCallIds.has(p.toolCallId),
      );
      if (stillOutstanding) {
        return;
      }
      setIsStreaming(false, chatId);
      streamingChatIdRef.current = null;
      clearParts();
    },
    [clearParts, setIsStreaming, streamingChatIdRef],
  );

  return { restorePendingApprovals, clearIfResolved };
}
