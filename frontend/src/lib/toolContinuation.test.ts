import { describe, expect, it } from 'vitest';
import { hasToolContinuation } from './toolContinuation';

describe('structured tool continuations', () => {
  it('joins a tool-only response to its final answer', () => {
    expect(
      hasToolContinuation({
        parts: [
          { type: 'text', text: 'checking' },
          { type: 'tool', toolName: 'run_command', state: 'completed' },
          { type: 'text', text: '' },
        ],
      })
    ).toBe(true);
  });
  it('ends the chain when a final answer follows the tools', () => {
    expect(
      hasToolContinuation({
        parts: [
          { type: 'tool', toolName: 'run_command', state: 'completed' },
          { type: 'text', text: 'final answer' },
        ],
      })
    ).toBe(false);
    expect(hasToolContinuation({ parts: [{ type: 'text', text: 'new reply' }] })).toBe(false);
  });
});
