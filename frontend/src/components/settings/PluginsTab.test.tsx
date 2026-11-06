import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import type { PluginBinary, PluginIntegration } from '../../lib/api';
import { BinaryRow, IntegrationRow } from './PluginsTab';

afterEach(() => vi.unstubAllGlobals());

const render = (integration: PluginIntegration, locale = 'en'): string => {
  vi.stubGlobal('localStorage', { getItem: () => locale });
  return renderToStaticMarkup(
    <I18nProvider>
      <IntegrationRow
        pluginId="p"
        integration={integration}
        onChange={async () => {}}
        t={(key) => key}
      />
    </I18nProvider>
  );
};

const base = { id: 'x', name: 'Notion', tokenHelpUrl: null } as const;

describe('plugin service sign-in', () => {
  it('offers a browser sign-in for an OAuth service', () => {
    const html = render({ ...base, auth: 'oauth', connected: false });
    expect(html).toContain('settings.plugins.connect');
    expect(html).toContain('settings.plugins.signInHint');
    expect(html).not.toContain('type="password"');
  });

  it('asks for a hidden token field for a token service', () => {
    const html = render({
      ...base,
      name: 'GitHub',
      auth: 'token',
      connected: false,
      tokenHelpUrl: 'https://github.com/settings/personal-access-tokens/new',
    });
    expect(html).toContain('type="password"');
    expect(html).toContain('settings.plugins.createToken');
  });

  it('offers to sign in again when a connected service stopped working', () => {
    const html = render({
      ...base,
      auth: 'oauth',
      connected: true,
      error: 'Sign in again from Settings → Plugins to use this service.',
    });
    expect(html).toContain('settings.plugins.reconnect');
    expect(html).toContain('settings.plugins.disconnect');
    expect(html).toContain('role="alert"');
  });

  it('shows a working connection with only a disconnect button', () => {
    const html = render({ ...base, auth: 'oauth', connected: true });
    expect(html).toContain('settings.plugins.connected');
    expect(html).not.toContain('settings.plugins.connect<');
    expect(html).toContain('settings.plugins.disconnect');
  });
});

const binary: PluginBinary = {
  name: 'agent-desktop',
  version: '1.0.2',
  package: 'agent-desktop',
  supported: true,
  installed: false,
  path: null,
  source: null,
  env: 'SUZENT_AGENT_DESKTOP_BIN',
  notice: '',
};

const renderBinary = (value: PluginBinary): string =>
  renderToStaticMarkup(
    <BinaryRow pluginId="desktop" binary={value} onChange={async () => {}} t={(key) => key} />
  );

describe('plugin programs', () => {
  it('offers to install a missing program', () => {
    const html = renderBinary(binary);
    expect(html).toContain('settings.plugins.installBinary');
    expect(html).toContain('settings.plugins.binaryMissing');
  });

  it('shows where an installed program lives, with no install button', () => {
    const html = renderBinary({ ...binary, installed: true, path: '/data/agent-desktop' });
    expect(html).toContain('/data/agent-desktop');
    expect(html).not.toContain('settings.plugins.installBinary');
  });

  it('says so when there is no build for this computer', () => {
    const html = renderBinary({ ...binary, supported: false });
    expect(html).toContain('settings.plugins.binaryUnsupported');
    expect(html).not.toContain('settings.plugins.installBinary');
  });
});
