import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { AcpAgentsTab } from './AcpAgentsTab';

afterEach(() => vi.unstubAllGlobals());

describe('ACP settings guidance', () => {
  it.each(['en', 'zh-CN'])(
    'separates connection directions with collapsed help in %s',
    (locale) => {
      vi.stubGlobal('localStorage', { getItem: () => locale });
      const html = renderToStaticMarkup(
        <I18nProvider>
          <AcpAgentsTab />
        </I18nProvider>
      );
      expect(html).toContain(locale === 'en' ? 'Editor connections' : '编辑器连接');
      expect(html).toContain(locale === 'en' ? 'External agents' : '外部代理');
      const help = html.match(/<details\b[^>]*>[\s\S]*?<\/details>/g) ?? [];
      expect(help).toHaveLength(2);
      expect(help.every((section) => !/^<details[^>]*\bopen\b/.test(section))).toBe(true);
      expect(help[0]).toContain('<code>suzent</code>');
      expect(help[0]).toContain('<code>acp</code>');
      expect(help[1]).toContain('~/.suzent/acp_agents.json');
      expect(html).not.toContain('settings.acp.');
    }
  );
});
