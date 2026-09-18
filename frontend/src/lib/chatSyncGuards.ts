import type { Message } from '../types/api';
import { isIntermediateStepContent, splitAssistantContent } from './chatUtils';

/**
 * Roles that open a new turn.
 *
 * The store and the server disagree on the label, not on the fact: a canvas
 * dispatch is appended locally as a `canvas_action` pill but persisted as a
 * plain `user` row, and cron/heartbeat runs come back as `system_triggered`.
 * All three prompt exactly one agent response, so all three have to advance
 * the counter — otherwise the same message lands in turn N locally and turn
 * N+1 on the server, which is precisely the misalignment this file exists to
 * prevent. `notice` is the odd one out: it is decoration, never a prompt.
 */
function startsTurn(message: Message): boolean {
  return (
    message.role === 'user' ||
    message.role === 'canvas_action' ||
    message.role === 'system_triggered'
  );
}

/**
 * A turn is everything the agent produced in response to one prompt, so its
 * index is simply how many prompts precede it. Comparing local and server
 * state only ever makes sense *within* one turn: these guards exist to hold
 * optimistic content while the backend catches up on the SAME turn, and
 * comparing the last assistant on each side compares two different messages
 * whenever one side already knows about a turn the other doesn't.
 */
function assistantForTurn(messages: Message[], turnIndex: number): Message | undefined {
  let turn = 0;
  let found: Message | undefined;
  for (const message of messages) {
    if (startsTurn(message)) {
      if (turn > turnIndex) break;
      turn += 1;
      continue;
    }
    if (turn === turnIndex && message.role === 'assistant') found = message;
  }
  return found;
}

function lastAssistantTurnIndex(messages: Message[]): number {
  let turn = 0;
  let lastAssistantTurn = -1;
  for (const message of messages) {
    if (startsTurn(message)) turn += 1;
    else if (message.role === 'assistant') lastAssistantTurn = turn;
  }
  return lastAssistantTurn;
}

/**
 * Pair up the assistant message the local store last wrote with the server's
 * assistant for that same turn.
 *
 * `server` being undefined while `local` is present means the server hasn't
 * written this turn yet — the one case where local content is genuinely newer.
 */
export function pairLastTurnAssistants(
  localMessages: Message[],
  serverMessages: Message[]
): { local?: Message; server?: Message; turnIndex: number } {
  const turnIndex = lastAssistantTurnIndex(localMessages);
  if (turnIndex < 0) return { turnIndex };
  return {
    local: assistantForTurn(localMessages, turnIndex),
    server: assistantForTurn(serverMessages, turnIndex),
    turnIndex,
  };
}

/**
 * Extract plain prose text from an assistant message, stripping out tool-call
 * and reasoning <details> blocks. Used to compare "real" content length.
 */
function extractProseContent(content: string): string {
  const blocks = splitAssistantContent(content);
  return blocks
    .filter((b) => b.type === 'markdown' || b.type === 'code')
    .map((b) => b.content)
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
 *
 * Both sides are read at the same turn. A snapshot that carries a turn the
 * local store has never seen is new information, not a regression.
 */
export function shouldKeepLocalAssistantContent(
  localMessages: Message[],
  serverMessages: Message[]
): boolean {
  const { local: localLastAssistant, server: serverLastAssistant } = pairLastTurnAssistants(
    localMessages,
    serverMessages
  );
  if (!localLastAssistant) return false;

  const localContent =
    typeof localLastAssistant.content === 'string' ? localLastAssistant.content.trim() : '';
  if (!localContent) return false;

  const localIsIntermediate = isIntermediateStepContent(localContent, localLastAssistant.stepInfo);
  if (localIsIntermediate) return false;

  if (!serverLastAssistant) return true;

  const serverContent =
    typeof serverLastAssistant.content === 'string' ? serverLastAssistant.content.trim() : '';
  const serverIsIntermediate = isIntermediateStepContent(
    serverContent,
    serverLastAssistant.stepInfo
  );
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
