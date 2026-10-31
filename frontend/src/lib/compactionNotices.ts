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
