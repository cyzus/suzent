import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { SocialTab } from './SocialTab';

function renderSocial(): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <SocialTab
        socialConfig={{
          memory_enabled: true,
          tools: ['search'],
          handshake: { enabled: false },
          telegram: { enabled: true, token: 'test-token', allowed_users: ['123'] },
          wechat: { enabled: false, bot_token: '', allowed_users: [] },
        }}
        tools={['search']}
        mcpServers={null}
        useCustomTools={false}
        useCustomMcp={false}
        onConfigChange={() => {}}
        onUseCustomToolsChange={() => {}}
        onUseCustomMcpChange={() => {}}
      />
    </I18nProvider>
  );
}

describe('Social channel settings', () => {
  it('prioritizes channels and counts only platform configurations', () => {
    const html = renderSocial();
    expect(html).toContain('1 / 2 enabled');
    expect(html.indexOf('Telegram')).toBeLessThan(html.indexOf('Agent Capabilities'));
    expect(html).not.toContain('settings.social.');
  });

  it('uses collapsed provider-style rows with separate connection and access sections', () => {
    const html = renderSocial();
    expect(html.match(/<details/g)).toHaveLength(2);
    expect(html).not.toContain('<details open');
    expect(html.match(/<summary/g)).toHaveLength(2);
    expect(html).toContain(
      'aria-pressed="true" aria-controls="social-channel-telegram-connection"'
    );
    expect(html).toContain('aria-pressed="false" aria-controls="social-channel-telegram-access"');
    expect(html).toContain('id="social-channel-telegram-access" hidden=""');
    expect(html).toContain('type="search"');
    expect(html).toContain('Log in with WeChat');
    expect(html).toContain('for="social-channel-telegram-token"');
    expect(html).toContain('type="password"');
    expect(html).toContain('value="123"');
  });
});
