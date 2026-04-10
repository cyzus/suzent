import type { Message } from '../types/api';
import { isIntermediateStepContent } from './chatUtils';

function getLastAssistantMessage(messages: Message[]): Message | undefined {
  return messages.length > 0
    ? [...messages].reverse().find((m) => m.role === 'assistant')
    : undefined;
}

/**
 * Keep optimistic local content when the server snapshot regresses to an
 * intermediate tool-only assistant message during postprocessing.
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

  return serverIsIntermediate;
}
