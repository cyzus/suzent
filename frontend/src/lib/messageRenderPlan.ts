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
    const message = messages[i];
    if (message.role === 'user' || !isIntermediateStepContent(message.content, message.stepInfo)) {
      i += 1;
      continue;
    }

    const groupStart = i;
    const allBlocks: ContentBlock[] = [];
    const allStepInfos: string[] = [];

    while (
      i < messages.length &&
      messages[i].role !== 'user' &&
      isIntermediateStepContent(messages[i].content, messages[i].stepInfo)
    ) {
      const parsedBlocks = filterIgnoredToolCalls(splitAssistantContent(messages[i].content));
      const stepBlocks = parsedBlocks.filter((block) => block.type === 'toolCall' || block.type === 'reasoning');
      if (stepBlocks.length > 0) {
        allBlocks.push(...stepBlocks);
      }
      const stepInfo = messages[i].stepInfo;
      if (stepInfo) {
        allStepInfos.push(stepInfo);
      }
      if (i > groupStart) {
        skipIndices.add(i);
      }
      i += 1;
    }

    if (
      i < messages.length &&
      messages[i].role !== 'user' &&
      !isIntermediateStepContent(messages[i].content, messages[i].stepInfo)
    ) {
      const nextStepInfo = messages[i].stepInfo;
      if (nextStepInfo) {
        allStepInfos.push(nextStepInfo);
      }
    }

    const stepSummary = summarizeStepInfos(allStepInfos);
    groupRenders.set(groupStart, {
      mergedBlocks: mergeToolCallPairs(allBlocks),
      stepSummary,
    });

    if (stepSummary && i < messages.length && messages[i].role !== 'user') {
      stepSummaryByMessageIndex.set(i, stepSummary);
    }
  }

  return { skipIndices, groupRenders, stepSummaryByMessageIndex };
}
