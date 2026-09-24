import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { ProvidersTab } from './ProvidersTab';
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
function render(tab: 'credentials' | 'models' = 'credentials'): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ProvidersTab
        providers={[provider]}
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
  it('starts collapsed with search and enabled-model count', () => {
    const html = render();
    expect(html).toContain('<details');
    expect(html).not.toContain('open=""');
    expect(html).toContain('Search providers');
    expect(html).toContain('1 models enabled');
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
});
