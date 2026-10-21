import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { FocalToolsPanelView } from './FocalToolsPanel';
import type { FocalPanel } from '../../lib/focalAgent';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}:${Object.values(values).join(',')}` : key,
  }),
}));

const panel: FocalPanel = {
  tools: [
    {
      id: 'FocalDispatchTool',
      name: 'Dispatch to sessions',
      description: 'Send work to a project session, or start a new one.',
      runtimeName: 'agent_dispatch',
    },
    {
      id: 'FocalScheduleTool',
      name: 'Schedule wake-ups',
      description: 'Schedule when SUZENT wakes next.',
      runtimeName: 'schedule_wakeup',
    },
  ],
  wakeups: [
    {
      id: 7,
      name: 'Stand-up',
      kind: 'reminder',
      schedule: 'once at 2026-10-20T09:00',
      scheduleKind: 'once',
      nextRunAt: '2026-10-20T09:00:00',
    },
    {
      id: 8,
      name: 'Check CI',
      kind: 'check',
      schedule: 'every 30m',
      scheduleKind: 'interval',
      nextRunAt: '2026-10-19T20:30:00',
      lastError: 'status_code: 404, model is no longer available',
    },
  ],
};
const render = (props: Partial<React.ComponentProps<typeof FocalToolsPanelView>> = {}): string =>
  renderToStaticMarkup(
    <FocalToolsPanelView
      panel={panel}
      loadError={false}
      cancelling={null}
      cancelError={false}
      onRetry={() => {}}
      onCancel={() => {}}
      {...props}
    />
  );

describe('Focal tools panel', () => {
  it('lists fixed tools read-only, with no picker or MCP switches', () => {
    const html = render();
    expect(html).toContain('focalTools.fixedNote');
    expect(html).toContain('Dispatch to sessions');
    expect(html).toContain('Schedule when SUZENT wakes next.');
    expect(html).not.toContain('type="checkbox"');
    expect(html).not.toContain('toolsPanel.mcpServers');
  });

  it('shows each wake-up with its kind, next run and a cancel button', () => {
    const html = render();
    expect(html).toContain('focalTools.reminder');
    expect(html).toContain('focalTools.check');
    expect(html).toContain('Stand-up');
    expect(html).toContain('focalTools.nextRun:');
    expect(html).toContain('every 30m');
    expect(html).not.toContain('once at 2026');
    expect(html).toContain('aria-label="focalTools.cancelAria:Stand-up"');
    expect(html).toContain('aria-label="focalTools.cancelAria:Check CI"');
  });

  it('disables cancelling while one is in flight and reports a failed cancel', () => {
    const html = render({ cancelling: 7, cancelError: true });
    expect(html.match(/disabled=""/g)).toHaveLength(2);
    expect(html).toContain('focalTools.cancelError');
  });

  it('explains an empty schedule and offers a retry when loading fails', () => {
    expect(render({ panel: { ...panel, wakeups: [] } })).toContain('focalTools.noWakeups');
    const failed = render({ panel: null, loadError: true });
    expect(failed).toContain('focalTools.loadError');
    expect(failed).toContain('focalTools.retry');
  });
  it('flags a wake-up whose last run failed, with the reason on hover', () => {
    const html = render();
    expect(html.match(/focalTools\.lastRunFailed/g)).toHaveLength(1);
    expect(html).toContain('title="status_code: 404, model is no longer available"');
  });
});
