import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { FocalBriefing } from './FocalBriefing';

vi.mock('../../i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

describe('Focal conversation opening', () => {
  it('only greets: the contact bar carries the name and what waits on the user', () => {
    const html = renderToStaticMarkup(<FocalBriefing />);
    expect(html).toContain('focalBriefing.greeting');
    expect(html).toContain('focalBriefing.invitation');
    expect(html).not.toContain('chatList.focal.name');
    expect(html).not.toContain('<details');
  });
});
