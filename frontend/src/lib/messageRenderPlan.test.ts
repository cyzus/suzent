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

  it('produces exactly one group representative per turn when intermediates are interrupted by text-bearing messages', () => {
    // Real-world regression: agent emits tool → text+tool → text+tool → final.
    // The middle "text+tool" messages are classified as non-intermediate because
    // they contain prose, so the old logic fragmented the turn into 3 groups.
    const messages: Message[] = [
      user('go'),
      assistant('<details><summary>🔧 bash_execute</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 10 | Output: 2'),
      assistant('Let me try another approach.\n<details><summary>🔧 read_file</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 20 | Output: 4'),
      assistant('Checking once more.\n<details><summary>🔧 grep_search</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 30 | Output: 5'),
      assistant('All done. Here is the answer.', 'Input: 5 | Output: 10'),
    ];

    const plan = buildMessageRenderPlan(messages);

    // Only the first intermediate (idx 1) gets a group representative.
    expect(Array.from(plan.groupRenders.keys())).toEqual([1]);
    // The step summary pill attaches to the first non-intermediate message.
    expect(plan.stepSummaryByMessageIndex.get(2)).toContain('4 steps');
  });

  it('treats system_triggered rows as turn boundaries so each cron/heartbeat fire has its own badge', () => {
    const toolCall = '<details><summary>🔧 bash_execute</summary><pre><code class="language-text">{}</code></pre></details>';
    const messages: Message[] = [
      { role: 'system_triggered', content: 'Scheduled Task: ingest' },
      assistant(toolCall, 'Input: 10 | Output: 2'),
      assistant('Run 1 done.', 'Input: 5 | Output: 6'),
      { role: 'system_triggered', content: 'Scheduled Task: ingest' },
      assistant(toolCall, 'Input: 20 | Output: 3'),
      assistant('Run 2 done.', 'Input: 5 | Output: 6'),
    ];

    const plan = buildMessageRenderPlan(messages);

    // One group representative per system-triggered fire.
    expect(Array.from(plan.groupRenders.keys()).sort((a, b) => a - b)).toEqual([1, 4]);
  });

  it('resets turn grouping at each user message', () => {
    const messages: Message[] = [
      user('first'),
      assistant('<details><summary>🔧 bash_execute</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 10 | Output: 2'),
      assistant('Reply 1'),
      user('second'),
      assistant('<details><summary>🔧 read_file</summary><pre><code class="language-text">{}</code></pre></details>', 'Input: 10 | Output: 3'),
      assistant('Reply 2'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(Array.from(plan.groupRenders.keys()).sort((a, b) => a - b)).toEqual([1, 4]);
  });
});
