import { getApiBase } from './api';

export interface BrowserPreferences {
  persistent: boolean;
  headless: boolean;
  channel: 'chromium' | 'chrome' | 'msedge';
}

export interface BrowserSettingsResponse {
  settings: BrowserPreferences;
  environment_overrides: Array<keyof BrowserPreferences>;
  available_browsers: Record<BrowserPreferences['channel'], boolean>;
}

export function browserChannelOptions(
  available: BrowserSettingsResponse['available_browsers'],
  t: (key: string) => string
): Array<{
  value: BrowserPreferences['channel'];
  label: string;
  disabled: boolean;
  hint?: string;
}> {
  return (['chromium', 'chrome', 'msedge'] as const).map((channel) => ({
    value: channel,
    label: t(`settings.browser.${channel === 'msedge' ? 'edge' : channel}`),
    disabled: channel !== 'chromium' && !available[channel],
    hint:
      channel === 'chromium'
        ? t('settings.browser.chromiumHelp')
        : !available[channel]
          ? t('settings.browser.notInstalled')
          : undefined,
  }));
}

export async function fetchBrowserSettings(): Promise<BrowserSettingsResponse> {
  const response = await fetch(`${getApiBase()}/browser/settings`);
  if (!response.ok) throw new Error('Failed to load browser settings');
  return response.json();
}

export async function saveBrowserSettings(
  settings: Partial<BrowserPreferences>
): Promise<BrowserSettingsResponse> {
  const response = await fetch(`${getApiBase()}/browser/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error('Failed to save browser settings');
  return response.json();
}
