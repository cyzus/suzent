import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { buildMessageRenderPlan } from './messageRenderPlan';

function assistant(content: string, stepInfo?: string): Message {
  return { role: 'assistant', content, stepInfo };
}

function user(content: string): Message {
  return { role: 'user', content };
}

describe('buildMessageRenderPlan', () => {
  it('groups consecutive tool-only assistant messages and marks non-representative indices as skipped', () => {
    const messages: Message[] = [
      assistant('<details><summary>🔧 read_file</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 100 | Output: 10'),
      assistant('<details><summary>🔧 grep_search</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 120 | Output: 20'),
      assistant('Final answer content', 'Input: 40 | Output: 30'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(plan.groupRenders.has(0)).toBe(true);
    expect(plan.skipIndices.has(1)).toBe(true);
    expect(plan.skipIndices.has(0)).toBe(false);
    expect(plan.stepSummaryByMessageIndex.get(2)).toContain('3 steps');
    expect(plan.stepSummaryByMessageIndex.get(2)).toContain('Input: 260 tokens');
    expect(plan.stepSummaryByMessageIndex.get(2)).toContain('Output: 60 tokens');
  });

  it('does not create step-group render for normal assistant or user messages', () => {
    const messages: Message[] = [
      user('hello'),
      assistant('plain markdown response'),
      assistant('another normal response'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(plan.groupRenders.size).toBe(0);
    expect(plan.skipIndices.size).toBe(0);
    expect(plan.stepSummaryByMessageIndex.size).toBe(0);
  });

  it('ignores final_answer tool calls when deciding intermediate step grouping', () => {
    const messages: Message[] = [
      assistant('<details><summary>🔧 final_answer</summary><pre><code class="language-text">ignored</code></pre></details>'),
      assistant('Visible response'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(plan.groupRenders.size).toBe(0);
    expect(plan.stepSummaryByMessageIndex.size).toBe(0);
  });

  it('keeps consecutive tool steps in one group across empty assistant placeholders', () => {
    const messages: Message[] = [
      assistant('<details><summary>🔧 bash_execute</summary><pre><code class="language-text">{"cmd":"a"}</code></pre></details>', 'Input: 10 | Output: 2'),
      assistant(''),
      assistant('<details><summary>🔧 bash_execute</summary><pre><code class="language-text">{"cmd":"b"}</code></pre></details>', 'Input: 20 | Output: 3'),
      assistant('Final answer body', 'Input: 5 | Output: 4'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(plan.groupRenders.has(0)).toBe(true);
    expect(plan.skipIndices.has(1)).toBe(true);
    expect(plan.skipIndices.has(2)).toBe(true);
    expect(plan.stepSummaryByMessageIndex.get(3)).toContain('3 steps');
    expect(plan.stepSummaryByMessageIndex.get(3)).toContain('Input: 35 tokens');
    expect(plan.stepSummaryByMessageIndex.get(3)).toContain('Output: 9 tokens');
  });
});
