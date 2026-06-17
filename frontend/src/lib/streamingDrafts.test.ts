import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { hideStreamingDrafts } from './streamingDrafts';

describe('hideStreamingDrafts', () => {
  it('hides backend streaming drafts while a transient stream is shown', () => {
    const user: Message = { role: 'user', content: 'run it' };
    const draft: Message = {
      role: 'assistant',
      content: '',
      _streaming_draft: true,
      parts: [{ type: 'tool', toolCallId: 'call-1', toolName: 'bash_execute', state: 'running' }],
    };
    const final: Message = { role: 'assistant', content: 'done' };

    expect(hideStreamingDrafts([user, draft, final], true)).toEqual([user, final]);
  });

  it('keeps drafts when no transient stream is visible', () => {
    const draft: Message = {
      role: 'assistant',
      content: '',
      _streaming_draft: true,
      parts: [{ type: 'reasoning', text: 'still working' }],
    };

    expect(hideStreamingDrafts([draft], false)).toEqual([draft]);
  });
});
