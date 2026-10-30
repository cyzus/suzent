import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryCount, MemoryDetails, MemoryPreview } from './MemorySummary';
import type { MemorySection } from '../../hooks/useMemorySection';
import { tForLocale } from '../../i18n';

vi.mock('../../hooks/useChatStore', () => ({
  useChatCoreStore: () => ({ switchToView: () => undefined }),
}));
vi.mock('../../hooks/useDreamStatus', () => ({
  useDreamStatus: () => ({ status: null, loading: true }),
}));
vi.mock('../../i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../i18n')>()),
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => tForLocale('en', key, params),
    locale: 'en',
  }),
}));

const used: MemorySection = {
  enabled: true,
  extracting: false,
  activity: {
    recalled: {
      items: [
        { id: 'm1', content: 'Prefers neutral grey themes' },
        { id: 'm2', content: 'Runs uv sync before tests' },
        { id: 'm3', content: 'Works in Shanghai time' },
      ],
      updated_at: '2026-10-20T09:00:00+00:00',
    },
    saved: [
      {
        date: '2026-10-20',
        time: '14:02',
        category: 'preference',
        kind: 'user',
        content: 'Prefers warm grey themes after all',
        revision: true,
      },
    ],
  },
};

describe('MemorySummary', () => {
  it('counts and previews the memories the latest turn used', () => {
    expect(renderToStaticMarkup(<MemoryCount section={used} />)).toBe('3 used');
    const preview = renderToStaticMarkup(<MemoryPreview section={used} />);
    expect(preview).toContain('Prefers neutral grey themes');
    expect(preview).not.toContain('Works in Shanghai time');
  });

  it('lists this turn, what the chat saved, and the organize hint', () => {
    const html = renderToStaticMarkup(<MemoryDetails section={used} />);
    expect(html).toContain('Used this turn');
    expect(html).toContain('Works in Shanghai time');
    expect(html).toContain('Updated');
    expect(html).toContain('Prefers warm grey themes after all');
    expect(html).toContain('Organizing');
    expect(html).toContain('Open memory');
  });

  it('keeps only the newest saved facts and counts the rest', () => {
    const fact = used.activity!.saved[0];
    const busy: MemorySection = {
      ...used,
      activity: {
        ...used.activity!,
        saved: [1, 2, 3, 4, 5].map((n) => ({ ...fact, content: `Fact ${n}`, revision: false })),
      },
    };
    const html = renderToStaticMarkup(<MemoryDetails section={busy} />);
    expect(html).toContain('Saved recently');
    expect(html).toContain('Fact 3');
    expect(html).not.toContain('Fact 4');
    expect(html).toContain('5 saved in this chat');
  });

  it('says when a turn used nothing and the chat is still saving', () => {
    const quiet: MemorySection = {
      enabled: true,
      extracting: true,
      activity: { recalled: { items: [], updated_at: null }, saved: [] },
    };
    expect(renderToStaticMarkup(<MemoryCount section={quiet} />)).toBe('');
    const html = renderToStaticMarkup(<MemoryDetails section={quiet} />);
    expect(html).toContain('None used this turn');
    expect(html).toContain('Saving...');
    expect(html).not.toContain('Nothing saved yet');
  });

  it('shows only that memory is off when disabled', () => {
    const off: MemorySection = { ...used, enabled: false };
    expect(renderToStaticMarkup(<MemoryCount section={off} />)).toBe('Off');
    expect(renderToStaticMarkup(<MemoryPreview section={off} />)).toBe('');
    expect(renderToStaticMarkup(<MemoryDetails section={off} />)).toBe('');
  });
});
