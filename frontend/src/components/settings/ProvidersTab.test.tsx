import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { buildCustomProvider, ProvidersTab, slugifyProviderId } from './ProvidersTab';
import type { ApiProvider } from '../../lib/api';

const provider: ApiProvider = {
  id: 'example',
  label: 'Example',
  fields: [
    {
      key: 'EXAMPLE_KEY',
      label: 'API Key',
      type: 'secret',
      placeholder: '',
      value: 'masked',
      isSet: true,
    },
  ],
  default_models: [{ id: 'example/model', name: 'Example model' }],
  models: [],
  user_config: { enabled_models: [], custom_models: [] },
};
beforeEach(() => {
  vi.stubGlobal('navigator', { language: 'en', languages: ['en'] });
});
function render(
  tab: 'credentials' | 'models' = 'credentials',
  currentProvider: ApiProvider = provider
): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ProvidersTab
        providers={[currentProvider]}
        apiKeys={{ EXAMPLE_KEY: 'test-secret-must-stay-hidden' }}
        userConfigs={{ example: { enabled_models: ['example/model'], custom_models: [] } }}
        showKey={{}}
        activeTabs={{ example: tab }}
        verifying={{}}
        verification={{ example: { success: true, message: 'Connection successful' } }}
        onKeyChange={vi.fn()}
        onToggleShowKey={vi.fn()}
        onTabChange={vi.fn()}
        onConfigChange={vi.fn()}
        onAddCustomModel={vi.fn()}
        onVerify={vi.fn()}
        onAddProvider={async () => {}}
        onDeleteProvider={async () => {}}
      />
    </I18nProvider>
  );
}
describe('Provider settings overview', () => {
  it('keeps subscription authentication mounted inside a collapsed card', () => {
    const html = render('credentials', {
      ...provider,
      id: 'chatgpt',
      label: 'ChatGPT Subscription',
      fields: [],
      user_config: { enabled_models: ['chatgpt/gpt-5'], custom_models: [] },
    });
    expect(html).toContain('<details');
    expect(html).not.toContain('open=""');
    const start = html.lastIndexOf('<summary');
    const summary = html.slice(start, html.indexOf('</summary>', start));
    expect(summary).toContain('ChatGPT Subscription');
    expect(summary).not.toContain('<button');
    expect(summary).not.toContain('Sign in with your ChatGPT account');
    expect(html).toContain('Sign In');
    expect(html).toContain('Not Signed In');
    const card = html.slice(html.lastIndexOf('<details'));
    expect(card.indexOf('Connection successful')).toBeLessThan(card.indexOf('</details>'));
  });
  it('starts collapsed with search and enabled-model count', () => {
    const html = render();
    expect(html).toContain('<details');
    expect(html).not.toContain('open=""');
    expect(html).toContain('Search providers');
    expect(html).toContain('1 models enabled');
    expect(html).toContain('1 enabled models · 1 providers');
    expect(html).toContain('Enabled models are not necessarily connected.');
    expect(html).not.toContain('settings.providers.');
  });
  it('masks stored credentials and shows inline verification', () => {
    const html = render();
    expect(html).not.toContain('test-secret-must-stay-hidden');
    expect(html).toContain('role="status"');
    expect(html).toContain('Connection successful');
  });
  it('offers model search and an accessible add-model action', () => {
    const html = render('models');
    expect(html).toContain('Search models by name or ID');
    expect(html).toContain('aria-label="Add model ID..."');
    expect(html).toContain('Example model');
  });
  it('shows fetched model details and keeps enabled models that were not fetched', () => {
    const html = render('models', {
      ...provider,
      models: [
        {
          id: 'example/new-model',
          name: 'New model',
          context_length: 128000,
          supports_vision: true,
          supports_reasoning: true,
          supports_function_calling: true,
        },
      ],
    });
    expect(html).toContain('New model');
    expect(html).toContain('128,000 token context');
    expect(html).toContain('Vision');
    expect(html).toContain('Reasoning');
    expect(html).toContain('Tools');
    expect(html).toContain('example/model');
  });
  it('picks a region instead of showing the Base URL field', () => {
    const regional: ApiProvider = {
      ...provider,
      key_url: 'https://keys.example.test/cn',
      regions: [
        { id: 'cn', name: 'China', base_url: 'https://cn.example.test/v1' },
        {
          id: 'global',
          name: 'Global',
          base_url: 'https://global.example.test/v1',
          key_url: 'https://keys.example.test/global',
        },
      ],
      split_accounts: true,
      fields: [
        ...provider.fields,
        {
          key: 'EXAMPLE_BASE_URL',
          label: 'Base URL',
          type: 'text',
          placeholder: '',
          value: 'https://global.example.test/v1',
          isSet: true,
        },
      ],
    };
    const html = renderToStaticMarkup(
      <I18nProvider>
        <ProvidersTab
          providers={[regional]}
          apiKeys={{ EXAMPLE_BASE_URL: 'https://global.example.test/v1/' }}
          userConfigs={{}}
          showKey={{}}
          activeTabs={{ example: 'credentials' }}
          verifying={{}}
          onKeyChange={vi.fn()}
          onToggleShowKey={vi.fn()}
          onTabChange={vi.fn()}
          onConfigChange={vi.fn()}
          onAddCustomModel={vi.fn()}
          onVerify={vi.fn()}
          onAddProvider={async () => {}}
          onDeleteProvider={async () => {}}
        />
      </I18nProvider>
    );
    expect(html).toContain('Region');
    expect(html).toMatch(/aria-checked="true"[^>]*>Global</);
    expect(html).toMatch(/aria-checked="false"[^>]*>China</);
    expect(html).toContain('https://keys.example.test/global');
    expect(html).toContain('pick the one your API key was created on');
    expect(html).not.toContain('aria-label="Base URL"');
    expect(html).not.toContain('>https://global.example.test/v1/<');
  });
  it('lists set-up providers as cards and the rest in a grouped catalog', () => {
    const unset = (id: string, label: string, group: ApiProvider['group']): ApiProvider => ({
      ...provider,
      id,
      label,
      group,
      fields: [{ ...provider.fields[0], key: `${id.toUpperCase()}_KEY`, isSet: false }],
    });
    const html = renderToStaticMarkup(
      <I18nProvider>
        <ProvidersTab
          providers={[
            provider,
            unset('kimi_code', 'Kimi Code', 'china'),
            unset('ollama', 'Ollama', 'local'),
          ]}
          apiKeys={{}}
          userConfigs={{}}
          showKey={{}}
          activeTabs={{}}
          verifying={{}}
          onKeyChange={vi.fn()}
          onToggleShowKey={vi.fn()}
          onTabChange={vi.fn()}
          onConfigChange={vi.fn()}
          onAddCustomModel={vi.fn()}
          onVerify={vi.fn()}
          onAddProvider={async () => {}}
          onDeleteProvider={async () => {}}
        />
      </I18nProvider>
    );
    // Only the provider with a saved key gets a card.
    expect(html.match(/<details/g)?.length).toBe(2); // the enabled summary and Example
    expect(html).toContain('title="Example"');
    // The catalog stays closed while something is set up.
    expect(html).not.toContain('China vendors');
    expect(html).not.toContain('Kimi Code');
  });
  it('opens the catalog when nothing is set up yet', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <ProvidersTab
          providers={[
            { ...provider, id: 'kimi_code', label: 'Kimi Code', group: 'china', fields: [] },
            { ...provider, id: 'ollama', label: 'Ollama', group: 'local', fields: [] },
          ]}
          apiKeys={{}}
          userConfigs={{}}
          showKey={{}}
          activeTabs={{}}
          verifying={{}}
          onKeyChange={vi.fn()}
          onToggleShowKey={vi.fn()}
          onTabChange={vi.fn()}
          onConfigChange={vi.fn()}
          onAddCustomModel={vi.fn()}
          onVerify={vi.fn()}
          onAddProvider={async () => {}}
          onDeleteProvider={async () => {}}
        />
      </I18nProvider>
    );
    expect(html).toContain('Add a provider');
    expect(html.indexOf('China vendors')).toBeLessThan(html.indexOf('Kimi Code'));
    expect(html.indexOf('Local &amp; self-hosted')).toBeLessThan(html.indexOf('Ollama'));
    expect(html).toContain('Custom endpoint');
    expect(html.match(/<details/g)?.length).toBe(1); // only the enabled summary
  });
});

describe('Custom provider', () => {
  it('derives an id the backend accepts from the name', () => {
    expect(slugifyProviderId('My Relay')).toBe('my_relay');
    expect(slugifyProviderId('  One-API (prod) ')).toBe('one_api_prod');
    expect(slugifyProviderId('302.AI')).toBe('p_302_ai');
    expect(slugifyProviderId('中转站')).toBe('');
  });
  it('gives the provider its own key and Base URL fields', () => {
    const { payload, keyField, baseUrlField } = buildCustomProvider({
      id: 'my_relay',
      label: ' My Relay ',
      protocol: 'anthropic',
      baseUrl: 'https://relay.example.test/',
      apiKey: 'sk-test',
    });
    expect(keyField).toBe('CUSTOM_MY_RELAY_API_KEY');
    expect(baseUrlField).toBe('CUSTOM_MY_RELAY_BASE_URL');
    expect(payload).toMatchObject({
      id: 'my_relay',
      label: 'My Relay',
      api_type: 'anthropic',
      base_url: 'https://relay.example.test',
      env_keys: ['CUSTOM_MY_RELAY_API_KEY'],
    });
    expect(payload.fields?.map((field) => field.key)).toEqual([keyField, baseUrlField]);
    expect(payload.api_key_optional).toBeUndefined();
  });
  it('marks a keyless endpoint as not needing a key', () => {
    const { payload } = buildCustomProvider({
      id: 'local_gw',
      label: 'Gateway',
      protocol: 'openai',
      baseUrl: 'http://localhost:4000/v1',
      apiKey: '',
    });
    expect(payload.api_key_optional).toBe(true);
  });
});
