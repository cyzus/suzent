import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { buildMessageRenderPlan, buildTurnWorkedSeconds } from './messageRenderPlan';

function assistant(content: string, stepInfo?: string): Message {
  return { role: 'assistant', content, stepInfo };
}

function user(content: string): Message {
  return { role: 'user', content };
}

describe('buildMessageRenderPlan', () => {
  it('groups consecutive tool-only assistant messages and marks non-representative indices as skipped', () => {
    const messages: Message[] = [
      assistant(
        '<details><summary>🔧 read_file</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 100 | Output: 10'
      ),
      assistant(
        '<details><summary>🔧 grep_search</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 120 | Output: 20'
      ),
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

  it('skips synthetic compaction summary rows that leaked into the display log', () => {
    const messages: Message[] = [
      user('original question'),
      assistant('original answer'),
      user(
        '[CONTEXT SUMMARY — READ BEFORE RESPONDING]\nThe following is an authoritative summary.'
      ),
      assistant('--- ARCHIVED CONTEXT SUMMARY ---\nsummary body\n--- END ARCHIVED CONTEXT ---'),
      user('new question'),
      assistant('new answer'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(plan.skipIndices.has(2)).toBe(true);
    expect(plan.skipIndices.has(3)).toBe(true);
    expect(plan.skipIndices.has(0)).toBe(false);
    expect(plan.skipIndices.has(5)).toBe(false);
  });

  it('ignores final_answer tool calls when deciding intermediate step grouping', () => {
    const messages: Message[] = [
      assistant(
        '<details><summary>🔧 final_answer</summary><pre><code class="language-text">ignored</code></pre></details>'
      ),
      assistant('Visible response'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(plan.groupRenders.size).toBe(0);
    expect(plan.stepSummaryByMessageIndex.size).toBe(0);
  });

  it('keeps consecutive tool steps in one group across empty assistant placeholders', () => {
    const messages: Message[] = [
      assistant(
        '<details><summary>🔧 run_command</summary><pre><code class="language-text">{"cmd":"a"}</code></pre></details>',
        'Input: 10 | Output: 2'
      ),
      assistant(''),
      assistant(
        '<details><summary>🔧 run_command</summary><pre><code class="language-text">{"cmd":"b"}</code></pre></details>',
        'Input: 20 | Output: 3'
      ),
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
      assistant(
        '<details><summary>🔧 run_command</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 10 | Output: 2'
      ),
      assistant(
        'Let me try another approach.\n<details><summary>🔧 read_file</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 20 | Output: 4'
      ),
      assistant(
        'Checking once more.\n<details><summary>🔧 grep_search</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 30 | Output: 5'
      ),
      assistant('All done. Here is the answer.', 'Input: 5 | Output: 10'),
    ];

    const plan = buildMessageRenderPlan(messages);

    // Only the first intermediate (idx 1) gets a group representative.
    expect(Array.from(plan.groupRenders.keys())).toEqual([1]);
    // The step summary pill attaches to the first non-intermediate message.
    expect(plan.stepSummaryByMessageIndex.get(2)).toContain('4 steps');
  });

  it('treats system_triggered rows as turn boundaries so each cron/heartbeat fire has its own badge', () => {
    const toolCall =
      '<details><summary>🔧 run_command</summary><pre><code class="language-text">{}</code></pre></details>';
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
      assistant(
        '<details><summary>🔧 run_command</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 10 | Output: 2'
      ),
      assistant('Reply 1'),
      user('second'),
      assistant(
        '<details><summary>🔧 read_file</summary><pre><code class="language-text">{}</code></pre></details>',
        'Input: 10 | Output: 3'
      ),
      assistant('Reply 2'),
    ];

    const plan = buildMessageRenderPlan(messages);

    expect(Array.from(plan.groupRenders.keys()).sort((a, b) => a - b)).toEqual([1, 4]);
  });
});

describe('buildTurnWorkedSeconds', () => {
  function at(message: Message, timestamp: string): Message {
    return { ...message, timestamp };
  }

  // Tool results are persisted as their own rows; the display `Message` union
  // only names the roles that render on their own.
  function toolResult(content: string, timestamp: string): Message {
    return { role: 'tool', content, timestamp } as unknown as Message;
  }

  it('spans the whole turn, not the gap to the first model response', () => {
    const messages: Message[] = [
      at(user('do the thing'), '2026-08-31T22:12:43.000Z'),
      at(assistant('<details><summary>🔧 bash</summary></details>'), '2026-08-31T22:12:52.000Z'),
      toolResult('ok', '2026-08-31T22:13:54.000Z'),
      at(assistant('all done'), '2026-08-31T22:14:00.000Z'),
    ];

    const worked = buildTurnWorkedSeconds(messages);

    // 22:12:43 -> 22:14:00, not the 9s to the first response.
    expect(worked.get(1)).toBe(77);
    expect(worked.get(3)).toBe(77);
  });

  it('measures each turn from its own user message', () => {
    const messages: Message[] = [
      at(user('first'), '2026-08-31T22:00:00.000Z'),
      at(assistant('one'), '2026-08-31T22:00:10.000Z'),
      at(user('second'), '2026-08-31T22:05:00.000Z'),
      at(assistant('two'), '2026-08-31T22:05:30.000Z'),
    ];

    const worked = buildTurnWorkedSeconds(messages);

    expect(worked.get(1)).toBe(10);
    expect(worked.get(3)).toBe(30);
  });

  it('ignores out-of-order rows and clock skew instead of reporting a negative span', () => {
    const messages: Message[] = [
      at(user('go'), '2026-08-31T22:14:00.000Z'),
      at(assistant('<details><summary>🔧 bash</summary></details>'), '2026-08-31T22:14:05.000Z'),
      // Concurrent tool results can land out of order.
      toolResult('b', '2026-08-31T22:14:31.000Z'),
      toolResult('a', '2026-08-31T22:14:30.000Z'),
      at(assistant('done'), '2026-08-31T22:14:20.000Z'),
    ];

    const worked = buildTurnWorkedSeconds(messages);

    expect(worked.get(1)).toBe(31);
  });

  it('omits a duration when the turn has no timestamps', () => {
    const worked = buildTurnWorkedSeconds([user('go'), assistant('done')]);

    expect(worked.size).toBe(0);
  });

  it('measures a turn the store coalesced into a single assistant bubble', () => {
    // The store folds a turn's tool rows and follow-up responses into one
    // bubble that keeps the first response's timestamp; the rows it absorbed
    // survive only as turn_last_activity_at.
    const messages: Message[] = [
      at(user('do the thing'), '2026-08-31T22:12:43.000Z'),
      {
        ...at(assistant('all done'), '2026-08-31T22:12:52.000Z'),
        turn_last_activity_at: '2026-08-31T22:14:00.000Z',
      },
    ];

    const worked = buildTurnWorkedSeconds(messages);

    expect(worked.get(1)).toBe(77);
  });

  it('omits a duration when the turn boundary is outside the list', () => {
    // A rendered window can start mid-turn; a duration measured from the first
    // visible assistant row would change as older messages load.
    const worked = buildTurnWorkedSeconds([
      at(assistant('continued'), '2026-08-31T22:12:52.000Z'),
      at(assistant('all done'), '2026-08-31T22:14:00.000Z'),
    ]);

    expect(worked.size).toBe(0);
  });

  it('omits a duration when the boundary clock runs ahead of the turn', () => {
    // An optimistic user row is stamped by the client; the rest by the backend.
    const worked = buildTurnWorkedSeconds([
      at(user('go'), '2026-08-31T22:14:10.000Z'),
      at(assistant('done'), '2026-08-31T22:14:00.000Z'),
    ]);

    expect(worked.has(1)).toBe(false);
  });
});
