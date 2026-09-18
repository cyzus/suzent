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
        content:
          '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>',
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
    const toolOnlyContent =
      '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>\n<details data-tool-call-id="t1"><summary>📦 tool</summary><pre><code class="language-text">result</code></pre></details>';
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
      { role: 'assistant', content: toolOnlyContent }, // post-process hasn't written final text yet
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
      {
        role: 'assistant',
        content:
          'This is a long and complete final answer with real prose content for the user. It explains everything clearly.',
      },
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
      {
        role: 'assistant',
        content: 'Server final answer that is reasonably long and authoritative.',
      },
    ];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });

  it('does not keep local content when local assistant is itself intermediate', () => {
    const local: Message[] = [
      { role: 'user', content: 'question' },
      {
        role: 'assistant',
        content:
          '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>',
      },
    ];
    const server: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Final answer from server.' },
    ];

    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });
  it('accepts a new turn whose reply is shorter than the previous turn (blank-until-refresh)', () => {
    // The confirmed-stream path deliberately appends nothing locally, so the local
    // store's last assistant belongs to the PREVIOUS turn. Comparing it with the new
    // turn's shorter reply used to reject the snapshot, leaving the chat blank until
    // the user refreshed.
    const previousReply =
      'I re-ran the change, kept the plain-text font substitution and the homepage link, ' +
      'and saved the updated file over the path you gave me. Open it and confirm.';
    const local: Message[] = [
      { role: 'user', content: 'update my resume' },
      { role: 'assistant', content: previousReply },
      { role: 'user', content: 'the font looks wrong' },
    ];
    const server: Message[] = [
      ...local,
      { role: 'assistant', content: 'Locked the fonts back to the originals.' },
    ];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });

  it('accepts a new turn that is still tool-only when the local store has no assistant for it', () => {
    const toolOnlyContent =
      '<details data-tool-call-id="t1"><summary>🔧 tool</summary><pre><code class="language-json">{"x":1}</code></pre></details>';
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'A complete earlier answer with real prose in it.' },
      { role: 'user', content: 'follow-up' },
    ];
    const server: Message[] = [...local, { role: 'assistant', content: toolOnlyContent }];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });

  it('still keeps local content when the server has not written this turn at all', () => {
    const local: Message[] = [
      { role: 'user', content: 'question' },
      { role: 'assistant', content: 'Optimistically appended final answer for the user.' },
    ];
    const server: Message[] = [{ role: 'user', content: 'question' }];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(true);
  });

  it('pairs a canvas dispatch with the user row the server persisted for it', () => {
    // The pill is local-only: the backend stores the same dispatch as a `user`
    // row. Counting only `user` puts the local assistant one turn behind the
    // server's, so the fresh reply gets compared with the short answer from the
    // previous turn and the complete snapshot is rejected as a regression.
    const local: Message[] = [
      { role: 'user', content: 'open the canvas' },
      { role: 'assistant', content: 'Done.' },
      { role: 'canvas_action', content: '[canvas: apply] "Apply"' },
      { role: 'assistant', content: 'Applying the two edits to the file you selected' },
    ];
    const server: Message[] = [
      { role: 'user', content: 'open the canvas' },
      { role: 'assistant', content: 'Done.' },
      { role: 'user', content: '[canvas: apply] "Apply"' },
      {
        role: 'assistant',
        content: 'Applying the two edits to the file you selected — both are in now.',
      },
    ];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });

  it('pairs a cron turn with its system_triggered prompt', () => {
    const local: Message[] = [
      { role: 'user', content: 'set up the digest' },
      { role: 'assistant', content: 'Scheduled it. I will post a digest every morning at nine.' },
      { role: 'system_triggered', content: '' },
    ];
    const server: Message[] = [...local, { role: 'assistant', content: 'Nothing new today.' }];
    expect(shouldKeepLocalAssistantContent(local, server)).toBe(false);
  });
});
