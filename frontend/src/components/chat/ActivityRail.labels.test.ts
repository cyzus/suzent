import { describe, expect, it } from 'vitest';

import type { AGUIPart } from '../../types/agui';
import {
  formatActivityToolName,
  getAguiActivityLabel,
  trailingToolRunLength,
} from './ActivityRail';

function toolPart(overrides: Partial<AGUIPart> = {}): AGUIPart {
  return {
    type: 'tool',
    toolCallId: 'call-1',
    toolName: 'run_command',
    output: 'done',
    state: 'completed',
    ...overrides,
  };
}

describe('formatActivityToolName', () => {
  it('describes the call with its own arguments', () => {
    expect(formatActivityToolName('read_file', JSON.stringify({ file_path: 'src/main.py' })))
      .toBe('Read main.py');
    expect(formatActivityToolName('run_command', JSON.stringify({ content: 'npm test', description: 'Run the tests' })))
      .toBe('Run the tests npm test');
  });

  it('falls back to the tool name while args are still streaming', () => {
    expect(formatActivityToolName('run_command')).toBe('Run command');
    expect(formatActivityToolName('run_command', '{"content": "npm ru')).toBe('Run command');
    expect(formatActivityToolName(undefined)).toBe('unknown tool');
  });
});

describe('trailingToolRunLength', () => {
  it('counts only the streak at the end of the run', () => {
    expect(trailingToolRunLength(['read_file', 'run_command', 'run_command'])).toBe(2);
    expect(trailingToolRunLength(['run_command', 'read_file'])).toBe(1);
    expect(trailingToolRunLength([])).toBe(0);
  });

  it('treats aliases of the same tool as one streak', () => {
    expect(trailingToolRunLength(['Bash', 'run_command', 'bash_execute'])).toBe(3);
  });
});

describe('getAguiActivityLabel', () => {
  it('collapses a run of the same tool into a count', () => {
    const items = [
      ...Array.from({ length: 9 }, () => toolPart()),
      toolPart({ output: undefined, state: 'running', args: '{"content": "npm test"}' }),
    ];
    const chunks = [{ chunk: { type: 'tool', items } }];

    expect(getAguiActivityLabel(chunks, true)).toBe('Ran 10 commands');
  });

  it('keeps counting a streak that the agent thought in the middle of', () => {
    const chunks = [
      { chunk: { type: 'tool', items: [toolPart(), toolPart()] } },
      { chunk: { type: 'reasoning', items: [{ type: 'reasoning', text: 'hmm' } as AGUIPart] } },
      { chunk: { type: 'tool', items: [toolPart({ output: undefined, state: 'running' })] } },
    ];

    expect(getAguiActivityLabel(chunks, true)).toBe('Ran 3 commands');
  });

  it('keeps describing the call until the streak is long enough to matter', () => {
    const items = [
      toolPart(),
      toolPart({ output: undefined, state: 'running', args: JSON.stringify({ content: 'npm test' }) }),
    ];
    const chunks = [{ chunk: { type: 'tool', items } }];

    expect(getAguiActivityLabel(chunks, true)).toBe('Run npm test');
  });

  it('describes a lone call instead of counting it', () => {
    const items = [
      toolPart({ toolName: 'read_file' }),
      toolPart({
        toolName: 'web_search',
        output: undefined,
        state: 'running',
        args: JSON.stringify({ query: 'tauri transparency' }),
      }),
    ];
    const chunks = [{ chunk: { type: 'tool', items } }];

    expect(getAguiActivityLabel(chunks, true)).toBe('Search the web “tauri transparency”');
  });
});
