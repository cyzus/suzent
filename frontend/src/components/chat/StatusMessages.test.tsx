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

function renderNotice(message: Parameters<typeof NoticeMessage>[0]['message'], resolved = false) {
  return renderToStaticMarkup(
    <I18nProvider>
      <NoticeMessage message={message} resolved={resolved} />
    </I18nProvider>
  );
}

describe('NoticeMessage', () => {
  it('draws a running compaction as a divider and holds the cube back', () => {
    const html = renderNotice({ role: 'notice', content: 'Auto compaction running...' });

    expect(html).toContain('role="separator"');
    expect(html).toMatch(/Compacting context…|正在压缩上下文…/);
    expect(html).not.toContain('suzent-cc-scene');
  });

  it('says a cold cache is why the prepared summary was used, and offers the summary', () => {
    const html = renderNotice({
      role: 'notice',
      content: 'Auto context compaction: 118.0k -> 19.0k tokens',
      timestamp: '2026-11-13T09:02:00Z',
      metadata: {
        kind: 'context_compaction',
        stage: 'complete',
        source: 'auto_midrun',
        tokens_before: 118_000,
        tokens_after: 19_000,
        reason: 'cold_cache',
        idle_seconds: 2820,
        summary: '## Goal\nShip it',
      },
    });

    expect(html).toContain('118K → 19K');
    expect(html).toMatch(/Away 47 min|离开 47 分钟/);
    expect(html).toMatch(/Show summary|查看摘要/);
    expect(html).not.toContain('Ship it');
  });

  it('reads the token counts of an older notice from its text', () => {
    const html = renderNotice({
      role: 'notice',
      content: 'Auto context compaction: 152.3k -> 18.4k tokens (64 -> 9 messages)',
    });

    expect(html).toContain('152.3K → 18.4K');
    expect(html).not.toMatch(/Show summary|查看摘要/);
  });

  it('marks a failure as kept history, or as resolved by a later retry', () => {
    const failed = renderNotice({
      role: 'notice',
      content: 'Auto context compaction failed: Compaction timed out. Original history preserved.',
    });
    expect(failed).toMatch(/Compaction timed out|压缩超时/);
    expect(failed).toMatch(/Original history kept|原有历史未改动/);
    expect(failed).toContain('text-brutal-red');

    const resolved = renderNotice({ role: 'notice', content: 'Compaction failed' }, true);
    expect(resolved).toMatch(/A later retry succeeded|后续重试已成功/);
    expect(resolved).not.toContain('text-brutal-red');
  });

  it('keeps the boxed layout for other notices, without an invalid time', () => {
    const html = renderNotice({
      role: 'notice',
      content: 'Images were dropped',
      timestamp: 'invalid',
    });
    expect(html).not.toContain('role="separator"');
    expect(html).toContain('Images were dropped');
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
