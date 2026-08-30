import { describe, expect, it } from 'vitest';

import type { AGUIPart } from '../../types/agui';
import { buildAguiActivityChunks, countActivityItems, groupActivityChunks } from './ActivityRail';

function activityGroups(parts: AGUIPart[]) {
  const chunks = buildAguiActivityChunks(parts);
  return groupActivityChunks(
    chunks,
    (chunk) => chunk.type === 'tool' || chunk.type === 'reasoning'
  ).filter((group) => group.type === 'activity');
}

function tool(toolCallId: string, overrides: Partial<AGUIPart> = {}): AGUIPart {
  return { type: 'tool', toolCallId, toolName: 'run_command', output: 'done', ...overrides };
}

describe('buildAguiActivityChunks', () => {
  it('groups consecutive parts of the same type, preserving interleaved order', () => {
    const chunks = buildAguiActivityChunks([
      { type: 'reasoning', text: 'Planning.' },
      tool('a'),
      tool('b'),
      { type: 'text', text: 'Here is what I found.' },
      tool('c'),
    ]);

    expect(chunks.map((chunk) => chunk.type)).toEqual(['reasoning', 'tool', 'text', 'tool']);
    expect(chunks[1].items).toHaveLength(2);
  });

  // The stream opens a text message per assistant step, so a step that only
  // called tools left an empty text part between two tool chunks. It drew
  // nothing, but grouping counted it as prose and cut the rail in two -- a long
  // turn collapsed into one rail per step with no visible reason for the break.
  it('keeps a turn in one rail when its steps open empty text parts', () => {
    const groups = activityGroups([
      { type: 'text', text: '', messageId: 'm1' },
      { type: 'reasoning', text: 'Looking at the repo.' },
      tool('a'),
      { type: 'text', text: '   ', messageId: 'm2' },
      { type: 'reasoning', text: 'Reading the config.' },
      tool('b'),
      { type: 'text', text: '\n', messageId: 'm3' },
      { type: 'reasoning', text: 'Checking the tests.' },
      tool('c'),
    ]);

    expect(groups).toHaveLength(1);
    expect(countActivityItems(groups[0].type === 'activity' ? groups[0].chunks : [])).toBe(6);
  });

  it('still starts a new rail after prose the user can see', () => {
    const groups = activityGroups([
      { type: 'reasoning', text: 'Planning.' },
      tool('a'),
      { type: 'text', text: 'Found it.' },
      tool('b'),
    ]);

    expect(groups).toHaveLength(2);
  });

  it('drops parts that render nothing instead of counting them as steps', () => {
    const chunks = buildAguiActivityChunks([
      { type: 'reasoning', text: '' },
      { type: 'citation-sources', text: '' },
      tool('a'),
    ]);

    expect(chunks).toEqual([{ type: 'tool', items: [tool('a')] }]);
  });

  it('merges a tool part replayed under the same call id', () => {
    const chunks = buildAguiActivityChunks([
      tool('a', { output: undefined, state: 'running' }),
      tool('a', { output: 'finished', state: 'completed' }),
    ]);

    expect(chunks).toHaveLength(1);
    expect(chunks[0].items).toHaveLength(1);
    expect(chunks[0].items[0].output).toBe('finished');
    expect(chunks[0].items[0].state).toBe('completed');
  });
});
