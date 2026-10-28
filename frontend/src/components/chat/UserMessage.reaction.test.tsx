import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { UserMessage } from './UserMessage';

vi.mock('../../hooks/useChatStore', () => ({ useChatStore: () => ({ config: {} }) }));
vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));

describe('Regent message reactions and actions', () => {
  it('anchors a reaction to message content and keeps latest-message actions inside the row', () => {
    const html = renderToStaticMarkup(
      <UserMessage
        chatId="focal-suzent"
        message={{ role: 'user', content: 'Hello' }}
        reaction="👍"
        isLatest
        onEdit={() => {}}
        onRerun={() => {}}
      />
    );
    expect(html).toContain('regent-user-content-reacted');
    expect(html).toContain('regent-reaction-anchor');
    expect(html).toContain('chatMessage.regentReaction');
    expect(html).toContain('regent-user-actions');
    expect(html).toContain('chatMessage.edit');
    expect(html).toContain('chatMessage.rerun');
  });
  it('does not reserve a phantom user-label row beneath older Regent messages', () => {
    const html = renderToStaticMarkup(
      <UserMessage
        chatId="focal-suzent"
        message={{ role: 'user', content: 'Hello' }}
        reaction="👀"
      />
    );
    expect(html).toContain('regent-reaction-anchor');
    expect(html).not.toContain('regent-user-actions');
    expect(html).not.toContain('chatMessage.userLabel');
  });
  it('preserves ordinary chat actions and does not attach a Regent reaction there', () => {
    const html = renderToStaticMarkup(
      <UserMessage chatId="regular" message={{ role: 'user', content: 'Hello' }} reaction="👍" />
    );
    expect(html).not.toContain('regent-reaction-anchor');
    expect(html).toContain('chatMessage.userLabel');
  });
});
