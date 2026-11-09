import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { StreamingPeekButton } from './StreamingPeekButton';

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
});
