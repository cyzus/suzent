import type { Message } from '../types/api';
import { isIntermediateStepContent, splitAssistantContent, mergeToolCallPairs, type ContentBlock } from './chatUtils';

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

function isEmptyAssistantPlaceholder(message: Message): boolean {
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
          (block) => block.type === 'toolCall' || block.type === 'reasoning',
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
