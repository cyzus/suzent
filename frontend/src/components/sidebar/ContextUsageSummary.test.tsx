import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ContextUsageSummary } from './ContextUsageSummary';
import { useContextUsageStore } from '../../hooks/useContextUsageStore';
import { tForLocale } from '../../i18n';

vi.mock('../../hooks/useChatStore', () => ({
  useChatCoreStore: () => ({
    config: { model: 'test' },
    backendConfig: { contextWindows: { test: 1000 } },
  }),
}));
vi.mock('../../hooks/useContextUsageStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/useContextUsageStore')>();
  const store = actual.useContextUsageStore;
  return {
    useContextUsageStore: Object.assign(
      <T,>(selector: (state: ReturnType<typeof store.getState>) => T): T =>
        selector(store.getState()),
      store
    ),
  };
});
vi.mock('../../i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../i18n')>()),
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => tForLocale('en', key, params),
  }),
}));

describe('ContextUsageSummary', () => {
  beforeEach(() => useContextUsageStore.setState({ usageByChatId: {}, usage: null }));

  function seed(tokens: number): void {
    useContextUsageStore.getState().setUsageForChat('chat', {
      input_tokens: 300,
      output_tokens: 40,
      total_tokens: 340,
      context_tokens: tokens,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      requests: 1,
      context_breakdown: {
        method: 'character_estimate',
        estimated_tokens: tokens,
        reserve_tokens: 200,
        measured_input_tokens: 300,
        has_unmeasured_media: false,
        categories: [{ id: 'messages', tokens, items: [{ name: 'text', tokens }] }],
        deferred: [
          { id: 'mcp_tools', tokens: 2000, items: [{ name: 'remote_search', tokens: 2000 }] },
        ],
      },
    });
  }

  it('shows empty state for a different chat without leaking cached usage', () => {
    seed(400);
    expect(renderToStaticMarkup(<ContextUsageSummary chatId="other" />)).toContain(
      'No usage reported yet'
    );
  });

  it('keeps deferred tools outside the bar and reserves free capacity', () => {
    seed(400);
    const html = renderToStaticMarkup(<ContextUsageSummary chatId="chat" />);
    expect(html).toContain('40% used');
    expect(html).toContain('40.0%');
    expect(html).toContain('20.0%');
    expect(html).toContain('MCP tools (not loaded)');
    expect(html.match(/<details/g)).toHaveLength(1);
    expect(html).toContain('remote_search');
    expect(html).not.toContain('Assistant messages');
    expect(html).not.toContain('200.0%');
    expect(html).toContain('Last request input (provider reported)');
  });

  it('does not render negative free capacity or progress above 100', () => {
    seed(1200);
    const html = renderToStaticMarkup(<ContextUsageSummary chatId="chat" />);
    expect(html).toContain('120% used');
    expect(html).toContain('aria-valuenow="100"');
    expect(html).not.toContain('-20.0%');
    expect(html).not.toContain('NaN');
  });
});
