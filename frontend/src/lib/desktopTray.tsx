import { useEffect } from 'react';

import { useI18n } from '../i18n';
import { isDesktop } from './runtime';

/** Tell the native tray menu which language the app is using. */
export async function publishTrayLanguage(language: string, desktop: boolean): Promise<void> {
  if (!desktop) return;
  const { invoke } = await import('@tauri-apps/api/core');
  await invoke('set_tray_language', { language });
}

export function DesktopTrayLanguage(): null {
  const { locale } = useI18n();
  useEffect(() => {
    void publishTrayLanguage(locale, isDesktop()).catch(() => {
      // The shell has no tray on Linux, and older builds lack the command.
    });
  }, [locale]);
  return null;
}
