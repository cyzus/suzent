/**
 * Recovery plan for a rejected /chat/send (or /chat/steer-send) request.
 *
 * The composer commits its optimistic state — the user bubble, a cleared parts
 * list, `isStreaming` — before the POST resolves. A 409 means the backend
 * refused because the previous turn is *still producing output*, so tearing
 * that state down leaves the UI idle and blank while the response keeps
 * streaming into a queue nobody is reading. The turn is only visible again
 * after a manual refresh reloads it from the database.
 */

/** Which send-like call was rejected; selects the failure message. */
export type SendAction = 'send' | 'steer' | 'retry' | 'edit';

const FAILURE_KEYS: Record<SendAction, string> = {
  send: 'chatWindow.sendFailed',
  steer: 'chatWindow.steerFailed',
  retry: 'chatWindow.retryFailed',
  edit: 'chatWindow.editFailed',
};

export interface SendFailureRecovery {
  /** i18n key for the status-bar text; the caller resolves it with t(). */
  messageKey: string;
  /** Interpolation params for `messageKey`. */
  messageParams?: Record<string, unknown>;
  /** Status-bar severity. */
  tone: 'error' | 'info';
  /**
   * True when the backend is still streaming the previous turn: keep the
   * streaming indicator, re-seed the parts that were cleared optimistically,
   * reload the chat authoritatively so the local state the backend never
   * accepted is discarded, and re-attach to /chat/live instead of going idle.
   */
  reattach: boolean;
  /** True when the composer text should be handed back to the user. */
  restoreInput: boolean;
}

/**
 * Decide how to recover from a non-2xx response to a send-like request.
 *
 * @param status HTTP status returned by the endpoint.
 * @param action Which call was rejected.
 */
export function planSendFailureRecovery(status: number, action: SendAction): SendFailureRecovery {
  if (status === 409) {
    return {
      messageKey: 'chatWindow.sendConflict',
      tone: 'info',
      reattach: true,
      restoreInput: true,
    };
  }
  return {
    messageKey: FAILURE_KEYS[action],
    messageParams: { status },
    tone: 'error',
    reattach: false,
    restoreInput: false,
  };
}
