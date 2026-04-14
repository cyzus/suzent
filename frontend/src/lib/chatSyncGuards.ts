import type { Message } from '../types/api';
import { isIntermediateStepContent, splitAssistantContent } from './chatUtils';

function getLastAssistantMessage(messages: Message[]): Message | undefined {
  return messages.length > 0
    ? [...messages].reverse().find((m) => m.role === 'assistant')
    : undefined;
}

/**
 * Extract plain prose text from an assistant message, stripping out tool-call
 * and reasoning <details> blocks. Used to compare "real" content length.
 */
function extractProseContent(content: string): string {
  const blocks = splitAssistantContent(content);
  return blocks
    .filter(b => b.type === 'markdown' || b.type === 'code')
    .map(b => b.content)
    .join('')
    .trim();
}

/**
 * Keep optimistic local content when the server snapshot regresses to an
 * intermediate tool-only assistant message during postprocessing.
 *
 * Also protects against the case where the server has written tool blocks
 * (making the message look non-empty) but hasn't yet committed the final
 * prose reply — in that case the server message has no prose while the
 * optimistic local message has the full final answer.
 */
export function shouldKeepLocalAssistantContent(localMessages: Message[], serverMessages: Message[]): boolean {
  const localLastAssistant = getLastAssistantMessage(localMessages);
  if (!localLastAssistant) return false;

  const localContent = typeof localLastAssistant.content === 'string'
    ? localLastAssistant.content.trim()
    : '';
  if (!localContent) return false;

  const localIsIntermediate = isIntermediateStepContent(localContent, localLastAssistant.stepInfo);
  if (localIsIntermediate) return false;

  const serverLastAssistant = getLastAssistantMessage(serverMessages);
  if (!serverLastAssistant) return true;

  const serverContent = typeof serverLastAssistant.content === 'string'
    ? serverLastAssistant.content.trim()
    : '';
  const serverIsIntermediate = isIntermediateStepContent(serverContent, serverLastAssistant.stepInfo);
  if (serverIsIntermediate) return true;

  // Server message is non-empty and non-intermediate (contains some prose), but
  // may still be a partial/mid-postprocess snapshot where the final prose wasn't
  // fully committed yet.  Compare the prose-only portions: if local has substantial
  // prose and server has none (or far less), the backend is still catching up.
  const localProse = extractProseContent(localContent);
  const serverProse = extractProseContent(serverContent);
  if (localProse.length > 20 && serverProse.length < localProse.length * 0.5) {
    return true;
  }

  return false;
}
