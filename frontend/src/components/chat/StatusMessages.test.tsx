import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { NoticeMessage, SystemTriggeredMessage } from './StatusMessages';
import { I18nProvider } from '../../i18n';

function renderReminder(content: string): string {
  return renderToStaticMarkup(
    <SystemTriggeredMessage message={{ role: 'system_triggered', content }} />
  );
}

describe('NoticeMessage', () => {
  it('labels a resolved historical failure and shows its original time', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <NoticeMessage
          resolved
          message={{
            role: 'notice',
            content: 'Context compaction failed: timeout',
            timestamp: '2026-10-31T01:13:00Z',
          }}
        />
      </I18nProvider>
    );
    expect(html).toMatch(/A later retry succeeded|后续重试已成功/);
    expect(html).toContain('dateTime="2026-10-31T01:13:00Z"');
    expect(html).toContain('Context compaction failed: timeout');
  });

  it('does not claim an unresolved failure succeeded or show an invalid time', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <NoticeMessage
          message={{ role: 'notice', content: 'Compaction failed', timestamp: 'invalid' }}
        />
      </I18nProvider>
    );
    expect(html).not.toMatch(/A later retry succeeded|后续重试已成功/);
    expect(html).not.toContain('<time');
  });
});

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
      'Sub-agent finished\n\nResult\n<!-- suzent-agent-inbox:subagent-result-sub_123 -->'
    );

    expect(html).not.toContain('suzent-agent-inbox');
  });

  it('starts folded to its title when asked, however short the body', () => {
    const html = renderToStaticMarkup(
      <SystemTriggeredMessage
        message={{
          role: 'system_triggered',
          content: '**Scheduled Task: Stand-up reminder**\n\nRemind the user about stand-up',
        }}
        folded
      />
    );

    expect(html).toContain('Scheduled Task: Stand-up reminder');
    expect(html).toContain('grid-rows-[0fr]');
    expect(html).toContain('aria-expanded="false"');
  });
});
