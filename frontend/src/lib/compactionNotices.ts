import type { Message } from '../types/api';

export function compactionNoticeStage(message: Message): string | undefined {
  if (message.role !== 'notice') return undefined;
  if (message.metadata?.kind === 'context_compaction') return message.metadata.stage;
  if (/^Context compacted$/i.test(message.content)) return 'complete';
  // Older stored notices and live events did not retain structured metadata.
  if (/^(?:Auto )?(?:context )?compaction (?:failed|timed out)\b/i.test(message.content))
    return 'error';
  if (
    /^(?:Auto )?(?:context )?compact(?:ion|ed)(?::|\s+(?:complete|\d[\d.]*k?\s*->))/i.test(
      message.content
    )
  )
    return 'complete';
  return undefined;
}

export function resolvedCompactionFailures(messages: Message[]): Set<number> {
  const resolved = new Set<number>();
  let succeeded = false;
  for (let index = messages.length - 1; index >= 0; index--) {
    const stage = compactionNoticeStage(messages[index]);
    if (stage === 'complete') succeeded = true;
    if (stage === 'error' && succeeded) resolved.add(index);
  }
  return resolved;
}

/** Where a completed compaction's summary came from (see the backend's event). */
export type CompactionReason = 'prepared' | 'cold_cache' | 'fresh';

export interface CompactionNoticeDetails {
  stage: string;
  source: string;
  tokensBefore: number | null;
  tokensAfter: number | null;
  reason: CompactionReason | null;
  idleSeconds: number | null;
  summary: string | null;
  /** The backend's own text for a failure or skip. */
  detail: string | null;
}

const LEGACY_TOKENS = /(\d[\d.]*)(k?)\s*->\s*(\d[\d.]*)(k?)/i;
const REASONS: CompactionReason[] = ['prepared', 'cold_cache', 'fresh'];

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function legacyTokens(content: string): [number | null, number | null] {
  const match = LEGACY_TOKENS.exec(content);
  if (!match) return [null, null];
  const scale = (n: string, k: string) => Math.round(Number(n) * (k ? 1000 : 1));
  return [scale(match[1], match[2]), scale(match[3], match[4])];
}

function failureDetail(content: string): string | null {
  const colon = content.indexOf(':');
  const text = colon >= 0 ? content.slice(colon + 1).trim() : '';
  return text || null;
}

/**
 * Everything a compaction notice says, from its structured metadata where the
 * backend stored it and from the text of older notices otherwise. Undefined
 * for any other notice.
 */
export function compactionNoticeDetails(message: Message): CompactionNoticeDetails | undefined {
  const content = message.content?.trim() ?? '';
  const running = /running\.\.\.$/i.test(content) || /\bcompacting\b/i.test(content);
  const stage = running ? 'start' : compactionNoticeStage(message);
  if (!stage) return undefined;
  const meta = message.metadata ?? {};
  const [legacyBefore, legacyAfter] = legacyTokens(content);
  const reason = REASONS.find((r) => r === meta.reason) ?? null;
  return {
    stage,
    source: typeof meta.source === 'string' ? meta.source : 'auto',
    tokensBefore: numberOrNull(meta.tokens_before) ?? legacyBefore,
    tokensAfter: numberOrNull(meta.tokens_after) ?? legacyAfter,
    reason,
    idleSeconds: numberOrNull(meta.idle_seconds),
    summary: typeof meta.summary === 'string' && meta.summary.trim() ? meta.summary : null,
    detail:
      stage === 'error' || stage === 'skipped'
        ? ((typeof meta.message === 'string' ? meta.message : null) ?? failureDetail(content))
        : null,
  };
}

/** The latest finished or failed compaction in a chat, newest first. */
export function latestCompaction(
  messages: Message[]
): { details: CompactionNoticeDetails; timestamp: string | undefined } | undefined {
  for (let index = messages.length - 1; index >= 0; index--) {
    const details = compactionNoticeDetails(messages[index]);
    if (details && (details.stage === 'complete' || details.stage === 'error')) {
      return { details, timestamp: messages[index].timestamp };
    }
  }
  return undefined;
}
