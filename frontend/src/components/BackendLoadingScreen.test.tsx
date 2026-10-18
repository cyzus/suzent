import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BackendLoadingScreen } from './BackendLoadingScreen';

vi.mock('../i18n', () => ({
  getInitialLocale: () => 'en',
  tForLocale: (_locale: string, key: string) => key,
}));

afterEach(() => vi.unstubAllGlobals());

describe('startup recovery', () => {
  it.each([undefined, 'Backend unavailable'])(
    'offers recovery only after failure (error: %s)',
    (error) => {
      vi.stubGlobal('window', {});
      const html = renderToStaticMarkup(<BackendLoadingScreen error={error} />);
      expect(html.includes('app.reconnectStartup')).toBe(Boolean(error));
      expect(html.includes('app.recoveryHintWeb')).toBe(Boolean(error));
      expect(html.includes('role="progressbar"')).toBe(!error);
    }
  );

  it('keeps initialization free of retry controls and a custom title bar', () => {
    vi.stubGlobal('window', { __TAURI__: { window: { getCurrentWindow: () => ({}) } } });
    const html = renderToStaticMarkup(<BackendLoadingScreen progressHint={45} />);
    expect(html).not.toContain('app.recoveryHintDesktop');
    expect(html).not.toContain('titlebar.close');
    expect(html).toContain('aria-valuenow="45"');
  });
});
