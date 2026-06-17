import React from 'react';
import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { SettingsCard, SectionCardHeader } from './SettingsCard';
import { BrutalOnOff } from '../BrutalOnOff';

interface SecurityTabProps {
  sandboxEnabled: boolean;
  onSandboxEnabledChange: (enabled: boolean) => void;
}

export function SecurityTab({ sandboxEnabled, onSandboxEnabledChange }: SecurityTabProps): React.ReactElement {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <SettingsHeader
        title={t('settings.security.title')}
        subtitle={t('settings.security.subtitle')}
      />

      <SettingsCard>
        <SectionCardHeader
          iconTone="yellow"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          }
          title={t('config.sandbox.button')}
          description={sandboxEnabled ? t('config.sandbox.enabledDesc') : t('config.sandbox.disabledDesc')}
          actions={
            <BrutalOnOff checked={sandboxEnabled} onChange={onSandboxEnabledChange} />
          }
        />
      </SettingsCard>
    </div>
  );
}
