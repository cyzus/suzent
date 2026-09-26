import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../i18n';
import { RefreshButton } from './RefreshButton';

const render = (node: React.ReactElement): string =>
  renderToStaticMarkup(<I18nProvider>{node}</I18nProvider>);

describe('RefreshButton', () => {
  it('labels itself from the shared refresh string', () => {
    const html = render(<RefreshButton />);

    expect(html).toContain('aria-label="Refresh"');
    expect(html).toContain('title="Refresh"');
  });

  it('spins only while the refresh it triggered is in flight', () => {
    expect(render(<RefreshButton />)).not.toContain('animate-spin');
    expect(render(<RefreshButton spinning />)).toContain('animate-spin');
  });
});
