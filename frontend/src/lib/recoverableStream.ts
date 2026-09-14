/** Shared transport for the backend-owned snapshot/cursor protocol. */
export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

export interface StreamBatch {
  reset: boolean;
  events: StreamEvent[];
}

export class StreamRecoveryError extends Error {
  constructor(
    public readonly reason: 'unavailable' | 'persistence' | 'interrupted',
    message: string
  ) {
    super(message);
  }
}

class ProtocolError extends StreamRecoveryError {
  constructor(message: string, reason: 'unavailable' | 'persistence' = 'unavailable') {
    super(reason, message);
  }
}

function isStreamEvent(value: unknown): value is StreamEvent {
  return (
    typeof value === 'object' && value !== null && typeof (value as StreamEvent).type === 'string'
  );
}

function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, ms);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}

export async function* recoverableStream(
  url: string,
  body: Record<string, unknown>,
  signal: AbortSignal,
  onStart: () => void,
  startRequest?: { url: string; body: Record<string, unknown> }
): AsyncGenerator<StreamBatch> {
  let runId: string | undefined;
  let seq: number | undefined;
  let lastRunId: string | undefined;
  let started = false;
  let failures = 0;
  let initialRequest = startRequest;
  while (!signal.aborted) {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      // Start a turn at most once. A lost acknowledgement is recovered by
      // observing that chat, never by replaying a potentially accepted send.
      const request = initialRequest;
      initialRequest = undefined;
      const response = await fetch(request?.url ?? url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(request?.body ?? body),
          protocol: 1,
          run_id: runId,
          after_seq: seq,
        }),
        signal,
      });
      if (response.status === 204 && !started && !startRequest) return;
      if (response.status === 204)
        throw new ProtocolError('Stream recovery is no longer available');
      if (!response.ok) {
        if (response.status < 500) throw new ProtocolError(`HTTP ${response.status}`);
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.body) throw new Error('Response body is null');
      if (!started) {
        started = true;
        onStart();
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) throw new Error('Stream disconnected before completion');
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() ?? '';
        for (const block of blocks) {
          const data = block
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n');
          if (!data) continue;
          const frame = JSON.parse(data) as Record<string, unknown>;
          if (
            typeof frame.run_id !== 'string' ||
            !Number.isSafeInteger(frame.seq) ||
            (frame.seq as number) < 0
          ) {
            throw new ProtocolError('Invalid stream cursor');
          }
          const nextSeq = frame.seq as number;
          if (frame.type === 'STREAM_SNAPSHOT') {
            if (!Array.isArray(frame.events) || !frame.events.every(isStreamEvent))
              throw new ProtocolError('Invalid stream snapshot');
            if (lastRunId !== undefined && lastRunId !== frame.run_id) onStart();
            lastRunId = frame.run_id;
            runId = frame.run_id;
            seq = nextSeq;
            failures = 0;
            yield { reset: true, events: frame.events as StreamEvent[] };
          } else if (frame.type === 'STREAM_EVENT') {
            if (!isStreamEvent(frame.event)) throw new ProtocolError('Invalid stream event');
            if (frame.run_id !== runId || seq === undefined || nextSeq > seq + 1) {
              // Ask for an authoritative reset, never append a suffix to a stale seed.
              runId = undefined;
              seq = undefined;
              throw new Error('Stream cursor gap');
            }
            if (nextSeq <= seq) continue;
            seq = nextSeq;
            failures = 0;
            yield { reset: false, events: [frame.event as StreamEvent] };
          } else if (frame.type === 'STREAM_END') {
            if (frame.superseded === true) {
              runId = undefined;
              seq = undefined;
              throw new Error('Stream replaced by a new run');
            }
            if (frame.run_id !== runId || nextSeq !== seq)
              throw new Error('Stream ended with a cursor gap');
            if (frame.persisted !== true)
              throw new ProtocolError('Stream persistence failed', 'persistence');
            return;
          } else {
            throw new ProtocolError('Unsupported stream protocol');
          }
        }
      }
    } catch (error) {
      if (signal.aborted || error instanceof ProtocolError) throw error;
      if (++failures > 5)
        throw new StreamRecoveryError('interrupted', 'Stream connection interrupted');
      await pause(Math.min(250 * 2 ** (failures - 1), 4000), signal);
    } finally {
      await reader?.cancel().catch(() => {});
      reader?.releaseLock();
    }
  }
  throw new DOMException('Aborted', 'AbortError');
}
