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

  it('keeps local final answer when server last assistant is tool-only and message counts match', () => {
    const toolOnlyContent = '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>\n<details data-tool-call-id="t1"><summary>📦 tool</summary><pre><code class="language-text">result</code></pre></details>';
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: toolOnlyContent },
      { role: 'user', content: 'follow-up' },
      { role: 'assistant', content: 'Final answer with real text for user.' },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: toolOnlyContent },
      { role: 'user', content: 'follow-up' },
      { role: 'assistant', content: toolOnlyContent },  // post-process hasn't written final text yet
    ];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(true);
  });

  it('keeps local final answer when server has tool blocks + tiny prose (post-process race)', () => {
    // Server has tool blocks plus a short non-prose fragment; local has the full final answer.
    // This simulates post-process partially writing the reply.
    const serverContent =
      '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>\n' +
      '<details data-tool-call-id="t1"><summary>📦 tool</summary><pre><code class="language-text">result text here</code></pre></details>';
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'This is a long and complete final answer with real prose content for the user. It explains everything clearly.' },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: serverContent },
    ];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(true);
  });

  it('does not keep local content when server has a comparable or richer prose answer', () => {
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Local final answer that is reasonably long.' },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Server final answer that is reasonably long and authoritative.' },
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
