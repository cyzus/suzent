import type { Message, RunTiming } from '../types/api';

/** Preserve each run when tool continuations are folded into one bubble. */
export function collectRunTimings(messages: Partial<Message>[]): RunTiming[] {
  const runs = new Map<string, RunTiming>();
  for (const message of messages) {
    const candidates = [...(message.run_timings ?? [])];
    if (message.run_started_at && message.run_finished_at && !message.run_timings?.length) {
      candidates.push({
        run_id: message._streaming_run_id ?? `${message.run_started_at}/${message.run_finished_at}`,
        started_at: message.run_started_at,
        finished_at: message.run_finished_at,
        active_seconds: message.run_active_seconds,
      });
    }
    for (const run of candidates) {
      const start = Date.parse(run.started_at);
      const end = Date.parse(run.finished_at);
      if (!run.run_id || !Number.isFinite(start) || !Number.isFinite(end) || end < start) continue;
      const unknownWait =
        run.unknown_wait ||
        (run.run_id === message._streaming_run_id &&
          run.active_seconds === undefined &&
          message.run_active_seconds === undefined &&
          message.parts?.some((part) => part.type === 'tool' && part.toolName === 'ask_question'));
      const previous = runs.get(run.run_id);
      runs.set(run.run_id, {
        ...run,
        active_seconds:
          run.active_seconds ??
          (run.run_id === message._streaming_run_id ? message.run_active_seconds : undefined) ??
          previous?.active_seconds,
        unknown_wait: Boolean(unknownWait || previous?.unknown_wait),
      });
    }
  }
  return [...runs.values()];
}

export function recordedWorkedSeconds(
  messages: Partial<Message>[],
  nowMs?: number
): number | undefined {
  const runs = collectRunTimings(
    messages.map((message) =>
      nowMs !== undefined &&
      message._streaming_draft &&
      message.run_started_at &&
      !message.run_finished_at
        ? { ...message, run_finished_at: new Date(nowMs).toISOString() }
        : message
    )
  );
  if (!runs.length) return undefined;
  if (runs.some((run) => run.unknown_wait && run.active_seconds === undefined)) return undefined;
  return Math.floor(
    runs.reduce(
      (total, run) =>
        total +
        (run.active_seconds !== undefined &&
        Number.isFinite(run.active_seconds) &&
        run.active_seconds >= 0
          ? run.active_seconds * 1000
          : Date.parse(run.finished_at) - Date.parse(run.started_at)),
      0
    ) / 1000
  );
}
