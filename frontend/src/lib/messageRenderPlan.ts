import type { Message } from '../types/api';
import {
  isIntermediateStepContent,
  splitAssistantContent,
  mergeToolCallPairs,
  type ContentBlock,
} from './chatUtils';

export interface StepGroupRender {
  mergedBlocks: ContentBlock[];
  stepSummary: string | null;
}

export interface MessageRenderPlan {
  skipIndices: Set<number>;
  groupRenders: Map<number, StepGroupRender>;
  stepSummaryByMessageIndex: Map<number, string>;
}

const IGNORED_TOOL_NAMES = ['final_answer', 'final answer'];

// Synthetic compaction summary messages are injected into the LLM context only.
// Older chats may have persisted them into the display log before this was
// fixed backend-side; hide them so users see only their original interactions.
const COMPACTION_SUMMARY_MARKERS = [
  '[CONTEXT SUMMARY — READ BEFORE RESPONDING]',
  '--- ARCHIVED CONTEXT SUMMARY ---',
];

function isCompactionSummaryMessage(message: Message): boolean {
  const content = message.content || '';
  return COMPACTION_SUMMARY_MARKERS.some((marker) => content.includes(marker));
}

function isEmptyAssistantPlaceholder(message: Message): boolean {
  if (message.parts && message.parts.length > 0) return false;
  return message.role !== 'user' && !message.content?.trim() && !message.stepInfo;
}

/**
 * A turn boundary separates one agent turn from the next.
 * Real user messages and system_triggered rows (cron, heartbeat, wake-parent) qualify.
 * Empty user rows are tool-resume continuations — they don't start a new turn.
 */
function isTurnBoundary(message: Message): boolean {
  if (message.role === 'system_triggered') return true;
  if (message.role !== 'user') return false;
  if ((message.content || '').trim().length > 0) return true;
  if (message.images && message.images.length > 0) return true;
  if (message.files && message.files.length > 0) return true;
  return false;
}

function parseTimestamp(value?: string): number | undefined {
  if (!value) return undefined;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * Wall-clock span of a turn: from the user message that opened it to the last
 * thing it produced.
 *
 * Both ends need care. The start is the turn boundary, not the previous row --
 * inside a turn the previous row is a tool result or a tool-resume stub. The
 * end is the *latest* timestamp anywhere in the turn rather than the last
 * message's: an assistant row is stamped when its model response *began*, so
 * the tool results it triggered are later than the response that asked for
 * them. Rows can also arrive slightly out of order (tool results from
 * concurrent calls), which a max ignores and a last-row read would not.
 */
function computeTurnWorkedSeconds(
  messages: Message[],
  boundaryIndex: number,
  turnStart: number,
  turnEnd: number
): number | undefined {
  // Without a boundary the turn's start is unknown -- which happens when the
  // opening user row sits outside the slice being rendered. Falling back to the
  // first assistant row would report a near-zero span that silently changes as
  // older messages load, so report nothing instead.
  if (boundaryIndex < 0) return undefined;
  const startedAt = parseTimestamp(messages[boundaryIndex].timestamp);
  if (startedAt === undefined) return undefined;

  let endedAt: number | undefined;
  for (let idx = turnStart; idx < turnEnd; idx += 1) {
    // `turn_last_activity_at` carries the rows the store folded into a
    // coalesced assistant bubble; `timestamp` alone is when that bubble's first
    // model response began.
    for (const stamp of [
      parseTimestamp(messages[idx].timestamp),
      parseTimestamp(messages[idx].turn_last_activity_at),
    ]) {
      if (stamp !== undefined && (endedAt === undefined || stamp > endedAt)) {
        endedAt = stamp;
      }
    }
  }
  if (endedAt === undefined) return undefined;

  // Clock skew -- an optimistic user row stamped by a client clock running
  // ahead of the backend -- can make a span read negative. Show nothing rather
  // than a bogus "Worked for 0s".
  if (endedAt < startedAt) return undefined;
  return Math.floor((endedAt - startedAt) / 1000);
}

/**
 * Wall-clock seconds the agent worked on the turn each assistant message
 * belongs to, keyed by that message's index. Every assistant row in a turn maps
 * to the same number: they are one stretch of work, and a rail must not report
 * only the slice between two adjacent rows.
 *
 * Build this from the *full* message list, not a rendered window: a slice can
 * start after the user row that opened a turn, and a turn's duration must not
 * depend on how much history happens to be loaded.
 */
export function buildTurnWorkedSeconds(messages: Message[]): Map<number, number> {
  const workedSecondsByMessageIndex = new Map<number, number>();

  let i = 0;
  while (i < messages.length) {
    if (messages[i].role !== 'assistant') {
      i += 1;
      continue;
    }

    let turnEnd = i;
    while (turnEnd < messages.length && !isTurnBoundary(messages[turnEnd])) {
      turnEnd += 1;
    }

    // The row that opened this turn -- scanned back from the first assistant
    // message, since the scan itself starts at that assistant row.
    let boundaryIndex = -1;
    for (let j = i - 1; j >= 0; j -= 1) {
      if (isTurnBoundary(messages[j])) {
        boundaryIndex = j;
        break;
      }
    }

    const workedSeconds = computeTurnWorkedSeconds(messages, boundaryIndex, i, turnEnd);
    if (workedSeconds !== undefined) {
      for (let idx = i; idx < turnEnd; idx += 1) {
        if (messages[idx].role === 'assistant') {
          workedSecondsByMessageIndex.set(idx, workedSeconds);
        }
      }
    }

    i = turnEnd;
  }

  return workedSecondsByMessageIndex;
}

function filterIgnoredToolCalls(blocks: ContentBlock[]): ContentBlock[] {
  return blocks.filter((block) => {
    if (block.type !== 'toolCall') return true;
    return !IGNORED_TOOL_NAMES.includes((block.toolName || '').toLowerCase());
  });
}

function summarizeStepInfos(stepInfos: string[]): string | null {
  if (stepInfos.length === 0) return null;

  let totalInput = 0;
  let totalOutput = 0;
  for (const info of stepInfos) {
    const inputMatch = info.match(/Input(?:\s+tokens)?:\s+([\d,]+)/i);
    const outputMatch = info.match(/Output(?:\s+tokens)?:\s+([\d,]+)/i);
    if (inputMatch) totalInput += parseInt(inputMatch[1].replace(/,/g, ''), 10);
    if (outputMatch) totalOutput += parseInt(outputMatch[1].replace(/,/g, ''), 10);
  }

  return `${stepInfos.length} steps | Input: ${totalInput.toLocaleString()} tokens | Output: ${totalOutput.toLocaleString()} tokens`;
}

export function buildMessageRenderPlan(messages: Message[]): MessageRenderPlan {
  const skipIndices = new Set<number>();
  const groupRenders = new Map<number, StepGroupRender>();
  const stepSummaryByMessageIndex = new Map<number, string>();

  // Hide any synthetic compaction summary rows that leaked into the display log.
  for (let k = 0; k < messages.length; k++) {
    if (isCompactionSummaryMessage(messages[k])) {
      skipIndices.add(k);
    }
  }

  let i = 0;
  while (i < messages.length) {
    // Skip user messages and non-assistant roles (notice, canvas_action) —
    // they render on their own and don't participate in turn-level badge logic.
    if (messages[i].role !== 'assistant') {
      i += 1;
      continue;
    }

    // A turn spans from the first assistant message after a real user message
    // (or the start) up to the next real user message (or end). Within a turn
    // we want exactly one SUZENT badge, regardless of how the assistant output
    // is split across multiple store messages. Empty user rows (system-reminder
    // residue between tool steps) are not turn boundaries.
    let turnEnd = i;
    while (turnEnd < messages.length && !isTurnBoundary(messages[turnEnd])) {
      turnEnd += 1;
    }

    const assistantIndicesInTurn: number[] = [];
    for (let j = i; j < turnEnd; j++) {
      if (messages[j].role === 'assistant') {
        assistantIndicesInTurn.push(j);
      }
    }

    const intermediateIndices: number[] = [];
    const finalIndices: number[] = [];
    const emptyIndices: number[] = [];
    for (const idx of assistantIndicesInTurn) {
      const msg = messages[idx];
      if (isEmptyAssistantPlaceholder(msg)) {
        emptyIndices.push(idx);
      } else if (msg.parts && msg.parts.length > 0) {
        finalIndices.push(idx);
      } else if (isIntermediateStepContent(msg.content, msg.stepInfo)) {
        intermediateIndices.push(idx);
      } else {
        finalIndices.push(idx);
      }
    }

    const allStepInfos: string[] = [];
    for (const idx of assistantIndicesInTurn) {
      const stepInfo = messages[idx].stepInfo;
      if (stepInfo) allStepInfos.push(stepInfo);
    }
    const stepSummary = summarizeStepInfos(allStepInfos);

    if (intermediateIndices.length > 0) {
      const groupStart = intermediateIndices[0];
      const allBlocks: ContentBlock[] = [];

      for (const idx of intermediateIndices) {
        const parsedBlocks = filterIgnoredToolCalls(splitAssistantContent(messages[idx].content));
        const stepBlocks = parsedBlocks.filter(
          (block) => block.type === 'toolCall' || block.type === 'reasoning'
        );
        if (stepBlocks.length > 0) {
          allBlocks.push(...stepBlocks);
        }
        if (idx !== groupStart) {
          skipIndices.add(idx);
        }
      }

      for (const idx of emptyIndices) {
        skipIndices.add(idx);
      }

      groupRenders.set(groupStart, {
        mergedBlocks: mergeToolCallPairs(allBlocks),
        stepSummary,
      });

      if (finalIndices.length > 0 && stepSummary) {
        stepSummaryByMessageIndex.set(finalIndices[0], stepSummary);
      }
    }

    i = turnEnd;
  }

  return { skipIndices, groupRenders, stepSummaryByMessageIndex };
}
