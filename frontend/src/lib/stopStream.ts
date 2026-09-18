/**
 * Asking the backend to stop a turn.
 *
 * Cancellation is cooperative: an accepted stop lets the turn drain, persist
 * whatever it produced and report its own STREAM_END{persisted:true}, so the
 * client keeps listening instead of tearing the connection down. Every other
 * outcome means no ending is coming on our account, and the caller falls back
 * to abandoning the stream locally.
 */
export type StopRequestResult =
  | { accepted: true }
  | { accepted: false; reason: 'no_active_stream' | 'error' | 'network'; status?: number };

export async function requestStopTurn(
  apiBase: string,
  chatId: string,
  reason: string,
  fetchImpl: typeof fetch = fetch
): Promise<StopRequestResult> {
  let res: Response;
  try {
    res = await fetchImpl(`${apiBase}/chat/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, reason }),
    });
  } catch {
    return { accepted: false, reason: 'network' };
  }
  if (res.ok) {
    // 200 does not by itself mean the turn was cancelled: /chat/stop also
    // answers 200 when all it could stop were background sub-agents, which
    // happens for a chat paused on tool approval — the parent's control handle
    // is already gone. Waiting for a STREAM_END that cannot come would sit on
    // "Stopping" until the fallback timer. `stream_stopped` says which it was;
    // an older backend omits it, and then 200 meant the turn.
    let streamStopped: unknown;
    try {
      streamStopped = (await res.json())?.stream_stopped;
    } catch {
      streamStopped = undefined;
    }
    if (streamStopped === false)
      return { accepted: false, reason: 'no_active_stream', status: 200 };
    return { accepted: true };
  }
  // 404 is "nothing to stop": the run already ended, or the backend has no
  // control handle for it. Not an error worth logging, just no STREAM_END.
  if (res.status === 404) return { accepted: false, reason: 'no_active_stream', status: 404 };
  return { accepted: false, reason: 'error', status: res.status };
}
