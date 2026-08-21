import { describe, it, expect } from 'vitest';
import { hasStreamedOutput } from './chatUtils';
import type { AGUIPart } from '../types/agui';

describe('hasStreamedOutput', () => {
  it('does not count the empty message the stream opens with', () => {
    // TEXT_MESSAGE_START arrives before the agent has produced a token. Under
    // ACP that gap is seconds long while the process boots, and treating it as
    // output replaced the assembly animation with an empty typewriter cursor.
    const parts: AGUIPart[] = [{ type: 'text', text: '', messageId: 'm1' }];
    expect(hasStreamedOutput(parts)).toBe(false);
  });

  it('counts the first real token', () => {
    const parts: AGUIPart[] = [{ type: 'text', text: 'H', messageId: 'm1' }];
    expect(hasStreamedOutput(parts)).toBe(true);
  });

  it('counts a tool call even before it returns', () => {
    const parts: AGUIPart[] = [
      { type: 'text', text: '', messageId: 'm1' },
      { type: 'tool', toolName: 'read_file', state: 'running' },
    ];
    expect(hasStreamedOutput(parts)).toBe(true);
  });

  it('treats no parts and an empty reasoning shell alike', () => {
    expect(hasStreamedOutput(undefined)).toBe(false);
    expect(hasStreamedOutput([])).toBe(false);
    expect(hasStreamedOutput([{ type: 'reasoning', text: '' }])).toBe(false);
  });
});
