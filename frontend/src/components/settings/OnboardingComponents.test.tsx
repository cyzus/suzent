import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { ProvidersTab } from './ProvidersTab';
import { ModelRolesTab } from './ModelRolesTab';

describe('onboarding component reuse', () => {
  it('hides provider management actions but retains other-service access', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <ProvidersTab
          onboarding
          providers={[]}
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
    expect(html).not.toContain('Sync capabilities');
    expect(html).not.toContain('Add Provider');
    expect(html).toContain('Use another service');
  });
  it('allows editing TTS assignments in place without opening voice settings', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <ModelRolesTab
          inlineVoiceModel
          roleModels={{ tts: ['p/voice'] }}
          suggestions={{ tts: ['p/voice'] }}
          unregisteredModels={[]}
          onChange={vi.fn()}
        />
      </I18nProvider>
    );
    expect(html).toContain('aria-controls="role-editor-tts"');
    expect(html).toContain('p/voice');
  });
});
