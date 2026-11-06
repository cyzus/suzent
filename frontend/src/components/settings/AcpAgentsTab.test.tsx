import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { AcpAgentsTab } from './AcpAgentsTab';

afterEach(() => vi.unstubAllGlobals());

describe('ACP settings guidance', () => {
  it.each(['en', 'zh-CN'])('shows editor configuration directly in %s', (locale) => {
    vi.stubGlobal('localStorage', { getItem: () => locale });
    const html = renderToStaticMarkup(
      <I18nProvider>
        <AcpAgentsTab />
      </I18nProvider>
    );
    expect(html).toContain(locale === 'en' ? 'Editor connections' : '编辑器连接');
    expect(html).toContain(locale === 'en' ? 'External agents' : '外部代理');
    expect(html).not.toContain('<details');
    expect(html).toContain('<code>suzent</code>');
    expect(html).toContain('<code>acp</code>');
    expect(html).not.toContain('~/.suzent/acp_agents.json');
    expect(html).not.toContain('settings.acp.');
  });
});
