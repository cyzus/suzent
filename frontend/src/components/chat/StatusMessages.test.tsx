import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SystemTriggeredMessage } from './StatusMessages';

function renderReminder(content: string): string {
  return renderToStaticMarkup(
    <SystemTriggeredMessage message={{ role: 'system_triggered', content }} />,
  );
}

describe('SystemTriggeredMessage', () => {
  it('shows short reminder bodies by default', () => {
    const html = renderReminder('Heartbeat check\n\nNothing pending.');

    expect(html).toContain('grid-rows-[1fr]');
    expect(html).toContain('aria-expanded="true"');
  });

  it('collapses long reminder bodies by default', () => {
    const html = renderReminder(`Sub-agent finished\n\n${'Result details. '.repeat(60)}`);

    expect(html).toContain('grid-rows-[0fr]');
    expect(html).toContain('aria-expanded="false"');
  });

  it('does not render durable inbox markers', () => {
    const html = renderReminder(
      'Sub-agent finished\n\nResult\n<!-- suzent-agent-inbox:subagent-result-sub_123 -->',
    );

    expect(html).not.toContain('suzent-agent-inbox');
  });
});
