import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { Message } from '../../types/api';
import { UserMessage } from './UserMessage';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, vars?: Record<string, string>) =>
      vars ? `${key}(${Object.values(vars).join(',')})` : key,
  }),
}));
vi.mock('../../hooks/useChatStore', () => ({
  useChatStore: () => ({ config: {} }),
}));
vi.mock('./MessageActionMenu', () => ({ MessageActionMenu: () => null }));

function render(metadata: Record<string, unknown>): string {
  const message = {
    role: 'user',
    content: 'summarize the notes',
    metadata,
  } as unknown as Message;
  return renderToStaticMarkup(<UserMessage message={message} chatId="chat-1" />);
}

describe('a prompt relayed by an ACP client', () => {
  it('names the person who wrote it and folds the background away', () => {
    const html = render({
      source: 'acp',
      sender: 'butter',
      channel: 'enoxian · suzent-vid',
      context: '<context>members</context>',
    });

    expect(html).toContain('chatMessage.sentVia(butter,enoxian · suzent-vid)');
    expect(html).toContain('summarize the notes');
    expect(html).toMatch(/<details[^>]*>(?!.*\sopen)/);
    expect(html).toContain('chatMessage.promptContext(0.1)');
    expect(html).toContain('&lt;context&gt;members&lt;/context&gt;');
  });

  it('keeps the background with the sender, above the request', () => {
    const html = render({
      source: 'acp',
      sender: 'butter',
      channel: 'enoxian',
      context: '<context>members</context>',
    });

    const sender = html.indexOf('chatMessage.sentVia');
    const fold = html.indexOf('chatMessage.promptContext');
    const request = html.indexOf('summarize the notes');
    expect(sender).toBeLessThan(fold);
    expect(fold).toBeLessThan(request);
  });

  it('shows no fold when nothing was hidden', () => {
    const html = render({ source: 'acp', sender: 'Zed', channel: 'ACP' });

    expect(html).not.toContain('<details');
  });
});
