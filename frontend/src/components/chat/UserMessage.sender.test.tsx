import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { UserMessage } from './UserMessage';

vi.mock('../../hooks/useChatStore', () => ({ useChatStore: () => ({ config: {} }) }));
vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

describe('who a prompt came from', () => {
  it.each([
    [{ source: 'acp', sender: 'Zed', channel: 'ACP' }, 'Zed', 'ACP'],
    [{ source: 'social', sender: 'Alice', channel: 'Telegram' }, 'Alice', 'Telegram'],
  ])('names the sender and the channel of %j', (metadata, sender, channel) => {
    const html = renderToStaticMarkup(
      <UserMessage chatId="chat-1" message={{ role: 'user', content: 'hi', metadata }} />
    );
    expect(html).toContain('chatMessage.sentVia');
    expect(html).toContain(sender);
    expect(html).toContain(channel);
  });

  it('shows the label a caller gives instead', () => {
    const html = renderToStaticMarkup(
      <UserMessage
        chatId="chat-1"
        message={{ role: 'user', content: 'hi' }}
        senderLabel="Sent by Regent"
      />
    );
    expect(html).toContain('Sent by Regent');
  });

  it('leaves a message typed here unlabelled', () => {
    const html = renderToStaticMarkup(
      <UserMessage chatId="chat-1" message={{ role: 'user', content: 'hello' }} />
    );
    expect(html).not.toContain('chatMessage.sentVia');
  });
});
