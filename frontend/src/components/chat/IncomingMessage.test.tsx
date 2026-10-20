import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { processEvent } from '../../hooks/useAGUI';
import { buildAguiActivityChunks } from './ActivityRail';
import { IncomingMessage } from './IncomingMessage';

vi.mock('../../i18n', () => ({
  useI18n: () => ({ locale: 'en', t: (key: string) => key }),
}));
vi.mock('./UserMessage', () => ({
  UserMessage: ({ message }: { message: { content: string } }) => (
    <div data-user-bubble>{message.content}</div>
  ),
}));

const fromSuzent =
  '[Agent message from SUZENT (focal-suzent)]\n<!-- suzent-agent-inbox:m1 -->\nAim it at the GitHub page instead.';

describe('a message taken in mid-turn', () => {
  it('lands in the live reply in order', () => {
    const { parts } = processEvent(
      {
        type: 'CUSTOM',
        data: { type: 'CUSTOM', name: 'incoming_message', value: { content: fromSuzent } },
      },
      [{ type: 'text', text: 'Working on the page.' }]
    );

    expect(buildAguiActivityChunks(parts).map((chunk) => chunk.type)).toEqual([
      'text',
      'incoming-message',
    ]);
  });

  it("shows SUZENT's request as the user's message", () => {
    const html = renderToStaticMarkup(<IncomingMessage text={fromSuzent} />);

    expect(html).toContain('data-user-bubble');
    expect(html).toContain('Aim it at the GitHub page instead.');
    expect(html).toContain('chatMessage.sentBySuzent');
    expect(html).not.toContain('suzent-agent-inbox');
  });

  it('shows any other message as a trigger card', () => {
    const html = renderToStaticMarkup(
      <IncomingMessage text={'[Agent message from Ops (chat-9)]\nPlease check the deploy'} />
    );

    expect(html).not.toContain('data-user-bubble');
    expect(html).toContain('Please check the deploy');
  });
});
