import React from 'react';
import { BellIcon, SpeakerWaveIcon } from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import { isWeb } from '../../lib/runtime';
import {
  NOTIFICATION_SOUND_OPTIONS,
  NOTIFICATION_WHEN_OPTIONS,
  useNotificationPreferences,
  type NotificationSound,
} from '../../lib/notificationPreferences';
import { playNotificationSound } from '../../lib/notificationSound';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalIconButton } from '../BrutalButton';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';
import { SettingsChoiceGroup } from './SettingsChoiceGroup';

export function NotificationsTab(): React.ReactElement {
  const { t } = useI18n();
  const { preferences, setWhen, setSound } = useNotificationPreferences();

  const whenOptions = NOTIFICATION_WHEN_OPTIONS.map((value) => ({
    value,
    label: t(`settings.notifications.when.${value}`),
  }));
  const soundOptions = NOTIFICATION_SOUND_OPTIONS.map((value) => ({
    value,
    label: t(`settings.notifications.sounds.${value}`),
  }));

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.notifications.title')} />

      <SettingsCard>
        <SectionCardHeader
          icon={<BellIcon className="h-5 w-5" aria-hidden="true" />}
          title={t('settings.notifications.whenTitle')}
        />
        <SettingsChoiceGroup
          label={t('settings.notifications.whenTitle')}
          value={preferences.when}
          onChange={setWhen}
          options={whenOptions}
        />
      </SettingsCard>

      <SettingsCard>
        <SectionCardHeader
          icon={<SpeakerWaveIcon className="h-5 w-5" aria-hidden="true" />}
          title={t('settings.notifications.soundTitle')}
        />
        <div className="flex items-center gap-2">
          <BrutalSelect
            value={preferences.sound}
            onChange={(value) => {
              const sound = value as NotificationSound;
              setSound(sound);
              playNotificationSound(sound);
            }}
            options={soundOptions}
            className="w-full max-w-sm"
          />
          <BrutalIconButton
            type="button"
            label={t('settings.previewSound')}
            disabled={preferences.sound === 'none'}
            onClick={() => playNotificationSound(preferences.sound)}
          >
            <SpeakerWaveIcon className="h-5 w-5" aria-hidden="true" />
          </BrutalIconButton>
        </div>
      </SettingsCard>

      {isWeb() && (
        <SettingsCard>
          <SectionCardHeader
            title={t('settings.notifications.desktopNoteTitle')}
            description={t('settings.notifications.desktopNoteDesc')}
          />
        </SettingsCard>
      )}
    </SettingsPage>
  );
}
