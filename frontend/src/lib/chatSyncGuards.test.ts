import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { shouldKeepLocalAssistantContent } from './chatSyncGuards';

describe('shouldKeepLocalAssistantContent', () => {
  it('keeps local final answer when server regresses to tool-only intermediate content', () => {
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Final answer text for user.' },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      {
        role: 'assistant',
        content: '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>',
      },
    ];

    expect(shouldKeepLocalAssistantContent(local, server)).toBe(true);
  });

  it('does not keep local content when server has a non-intermediate assistant reply', () => {
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Older local final answer.' },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Authoritative server final answer.' },
    ];

    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });

  it('does not keep local content when local assistant is itself intermediate', () => {
    const local: Message[] = [
      { role: 'user', content: 'question' },
      {
        role: 'assistant',
        content: '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>',
      },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Final answer from server.' },
    ];

    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });
});
