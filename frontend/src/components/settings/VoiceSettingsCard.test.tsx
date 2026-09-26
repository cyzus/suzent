import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { VoiceSettingsCard } from './VoiceSettingsCard';
import { ModelRolesTab } from './ModelRolesTab';

it('separates speech controls from role assignment and links both pages', () => {
  const voice = renderToStaticMarkup(
    <I18nProvider>
      <VoiceSettingsCard />
    </I18nProvider>
  );
  expect(voice).toContain('bg-white');
  expect(voice).not.toContain('Choose the API speech model');
  const roles = renderToStaticMarkup(
    <I18nProvider>
      <ModelRolesTab
        roleModels={{ tts: ['old-provider/voice'] }}
        suggestions={{}}
        unregisteredModels={[]}
        onChange={() => {}}
        onOpenVoiceSettings={() => {}}
      />
    </I18nProvider>
  );
  expect(roles).toContain('Voice &amp; playback settings');
  expect(roles).toContain('old-provider/voice');
  expect(roles).not.toContain('Choose the API speech model');
});
