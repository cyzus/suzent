import { getApiBase } from './api';

export interface BrowserPreferences {
  connection_mode: 'managed' | 'existing' | 'extension';
  persistent: boolean;
  headless: boolean;
  channel: 'chromium' | 'chrome' | 'msedge';
}

export interface BrowserSettingsResponse {
  settings: BrowserPreferences;
  environment_overrides: Array<keyof BrowserPreferences>;
  available_browsers: Record<BrowserPreferences['channel'], boolean>;
}

export function existingBrowserAvailable(data: BrowserSettingsResponse): boolean {
  return data.environment_overrides.includes('channel')
    ? data.settings.channel !== 'chromium' && data.available_browsers[data.settings.channel]
    : data.available_browsers.chrome || data.available_browsers.msedge;
}

export function connectionModeChange(
  data: BrowserSettingsResponse,
  connection_mode: BrowserPreferences['connection_mode']
): Partial<BrowserPreferences> {
  if (
    connection_mode === 'existing' &&
    data.settings.channel === 'chromium' &&
    !data.environment_overrides.includes('channel')
  ) {
    return { connection_mode, channel: data.available_browsers.msedge ? 'msedge' : 'chrome' };
  }
  return { connection_mode };
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
    headers: { 'Content-Type': 'application/json', 'X-Suzent-Browser-Setup': '1' },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error('Failed to save browser settings');
  return response.json();
}
