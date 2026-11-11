import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { isActiveTurnOutOfView, StreamingPeekButton } from './StreamingPeekButton';

vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));

describe('StreamingPeekButton', () => {
  it('renders hidden and non-interactive when visible is false', () => {
    const html = renderToStaticMarkup(<StreamingPeekButton visible={false} onClick={() => {}} />);

    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain('pointer-events-none');
  });

  it('renders interactive peeking head and hover-only arrow when visible is true', () => {
    const html = renderToStaticMarkup(<StreamingPeekButton visible={true} onClick={() => {}} />);

    expect(html).toContain('aria-hidden="false"');
    expect(html).toContain('tabindex="0"');
    expect(html).toContain('pointer-events-auto');
    expect(html).toContain('suzent-peek-head');
    expect(html).toContain('suzent-peek-eyes');
    expect(html).toContain('suzent-peek-arrow');
    expect(html).toContain('aria-label="chatWindow.scrollToBottom"');
  });

  it('keeps the button hidden while the latest user message or streaming reply is still in view', () => {
    const makeRow = (top: number, isUser = false) => ({
      classList: { contains: (cls: string) => isUser && cls === 'chat-msg-row-user' },
      getBoundingClientRect: () => ({ top }),
    });

    // User message starts at y=320 inside a 600px viewport -> still visible -> false
    const scrollerVisible = {
      getBoundingClientRect: () => ({ top: 0, bottom: 600, height: 600 }),
      querySelectorAll: () => [makeRow(100, false), makeRow(320, true), makeRow(420, false)],
    } as unknown as HTMLElement;
    expect(isActiveTurnOutOfView(scrollerVisible)).toBe(false);

    // Scrolled far up into history so the user message top is at y=640 (below 600px viewport) -> true
    const scrollerOutOfView = {
      getBoundingClientRect: () => ({ top: 0, bottom: 600, height: 600 }),
      querySelectorAll: () => [makeRow(100, false), makeRow(640, true), makeRow(740, false)],
    } as unknown as HTMLElement;
    expect(isActiveTurnOutOfView(scrollerOutOfView)).toBe(true);
  });
});
