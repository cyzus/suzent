import { useCallback } from 'react';
import { useI18n } from '../i18n';
import { notifyDesktop } from '../lib/desktopNotifications';

export function useNativeNotification(): (message: string) => void {
  const { t } = useI18n();
  return useCallback(
    (message: string): void => {
      void notifyDesktop(t('app.title'), message);
    },
    [t]
  );
}
