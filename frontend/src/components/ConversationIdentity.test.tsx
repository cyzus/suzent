import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const store = vi.hoisted(() => ({
  currentChatId: 'focal-suzent' as string | null,
  chats: [] as Array<{ id: string; title: string; projectName?: string }>,
}));

vi.mock('../hooks/useChatStore', () => ({
  useChatCoreStore: () => store,
  useChatStreamingStore: () => ({ isStreaming: false, activeStreamingChatId: null }),
  useChatStore: () => ({}),
}));
vi.mock('../i18n', () => ({
  useI18n: () => ({ locale: 'en', t: (key: string) => key }),
}));

import { ConversationIdentity } from './StatusBar';

const text = (): string =>
  renderToStaticMarkup(<ConversationIdentity />)
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

describe('ConversationIdentity', () => {
  beforeEach(() => {
    store.currentChatId = 'focal-suzent';
    store.chats = [];
  });

  it('shows Regent as a contact: Suzent Regent with its role', () => {
    expect(text()).toBe('chatList.focal.brand chatList.focal.name chatList.focal.role');
  });

  it('keeps a regular chat to its title and project', () => {
    store.currentChatId = 'chat-1';
    store.chats = [{ id: 'chat-1', title: 'Nav fix', projectName: 'Website' }];

    expect(text()).toBe('Nav fix Website');
  });
});
