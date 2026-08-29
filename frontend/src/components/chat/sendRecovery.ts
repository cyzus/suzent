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
export interface SendFailureRecovery {
  /** Status-bar text describing what happened. */
  message: string;
  /** Status-bar severity. */
  tone: 'error' | 'info';
  /**
   * True when the backend is still streaming the previous turn: keep the
   * streaming indicator, re-seed the parts that were cleared optimistically,
   * reload the chat to drop the user bubble that was never accepted, and
   * re-attach to /chat/live instead of going idle.
   */
  reattach: boolean;
  /** True when the composer text should be handed back to the user. */
  restoreInput: boolean;
}

/**
 * Decide how to recover from a non-2xx response to a send-like request.
 *
 * @param status HTTP status returned by the endpoint.
 * @param label Human-readable name of the action, used in the failure message.
 */
export function planSendFailureRecovery(status: number, label: string): SendFailureRecovery {
  if (status === 409) {
    return {
      message: 'Chat is still responding — reconnecting to the live response',
      tone: 'info',
      reattach: true,
      restoreInput: true,
    };
  }
  return {
    message: `${label} failed (${status})`,
    tone: 'error',
    reattach: false,
    restoreInput: false,
  };
}
