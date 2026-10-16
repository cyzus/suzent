import React from 'react';
import { BellIcon, SpeakerWaveIcon } from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import { isWeb } from '../../lib/runtime';
import {
  NOTIFICATION_SOUND_OPTIONS,
  NOTIFICATION_WHEN_OPTIONS,
  useNotificationPreferences,
  type NotificationSound,
  type NotificationWhen,
} from '../../lib/notificationPreferences';
import { playNotificationSound } from '../../lib/notificationSound';
import { BrutalSelect } from '../BrutalSelect';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

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
      <SettingsHeader
        title={t('settings.notifications.title')}
        subtitle={t('settings.notifications.subtitle')}
      />

      <SettingsCard>
        <SectionCardHeader
          icon={<BellIcon className="h-5 w-5" aria-hidden="true" />}
          title={t('settings.notifications.whenTitle')}
          description={t('settings.notifications.whenDesc')}
        />
        <BrutalSelect
          value={preferences.when}
          onChange={(value) => setWhen(value as NotificationWhen)}
          options={whenOptions}
          className="max-w-sm"
        />
      </SettingsCard>

      <SettingsCard>
        <SectionCardHeader
          icon={<SpeakerWaveIcon className="h-5 w-5" aria-hidden="true" />}
          title={t('settings.notifications.soundTitle')}
          description={t('settings.notifications.soundDesc')}
        />
        <BrutalSelect
          value={preferences.sound}
          onChange={(value) => {
            const sound = value as NotificationSound;
            setSound(sound);
            playNotificationSound(sound);
          }}
          options={soundOptions}
          className="max-w-sm"
        />
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
