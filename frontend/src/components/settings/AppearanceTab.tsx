import React from 'react';
import {
  useTheme,
  SCHEME_COLORS,
  SCHEME_SURFACES,
  type Scheme,
  type ThemeMode,
} from '../../hooks/useTheme';
import { useI18n, type Locale } from '../../i18n';
import { SettingsChoiceGroup } from './SettingsChoiceGroup';
import { SettingsHeader } from './SettingsHeader';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';

/** Mini split preview: left = light half, right = dark half */
function CardPreview({ s }: { s: Scheme }): React.ReactElement {
  const { light, dark } = SCHEME_COLORS[s];
  const { bg2, bg3 } = SCHEME_SURFACES[s];

  return (
    <div className="flex h-full">
      {/* Light half */}
      <div className="flex-1 bg-white flex flex-col gap-1.5 p-2">
        <div className="h-2 w-full rounded-sm" style={{ backgroundColor: light }} />
        <div className="h-1.5 w-4/5 bg-neutral-200 rounded-sm" />
        <div className="h-1.5 w-3/5 bg-neutral-200 rounded-sm" />
        <div
          className="mt-auto h-3.5 w-3/4 rounded-sm border border-neutral-200"
          style={{ backgroundColor: light }}
        />
      </div>

      <div className="w-px bg-neutral-200" />

      {/* Dark half */}
      <div className="flex-1 flex flex-col gap-1.5 p-2" style={{ backgroundColor: bg2 }}>
        <div className="h-2 w-full rounded-sm" style={{ backgroundColor: dark }} />
        <div className="h-1.5 w-4/5 rounded-sm" style={{ backgroundColor: bg3 }} />
        <div className="h-1.5 w-3/5 rounded-sm" style={{ backgroundColor: bg3 }} />
        <div
          className="mt-auto h-3.5 w-3/4 rounded-sm"
          style={{ backgroundColor: dark, border: `1px solid ${bg3}` }}
        />
      </div>
    </div>
  );
}

/** The same split as CardPreview, with one half or both depending on the mode. */
function ModePreview({ mode, scheme }: { mode: ThemeMode; scheme: Scheme }): React.ReactElement {
  const { light, dark } = SCHEME_COLORS[scheme];
  const { bg2, bg3 } = SCHEME_SURFACES[scheme];

  const lightHalf = (
    <div className="flex-1 bg-white flex flex-col gap-1.5 p-2">
      <div className="h-2 w-full rounded-sm" style={{ backgroundColor: light }} />
      <div className="h-1.5 w-4/5 bg-neutral-200 rounded-sm" />
      <div className="h-1.5 w-3/5 bg-neutral-200 rounded-sm" />
    </div>
  );
  const darkHalf = (
    <div className="flex-1 flex flex-col gap-1.5 p-2" style={{ backgroundColor: bg2 }}>
      <div className="h-2 w-full rounded-sm" style={{ backgroundColor: dark }} />
      <div className="h-1.5 w-4/5 rounded-sm" style={{ backgroundColor: bg3 }} />
      <div className="h-1.5 w-3/5 rounded-sm" style={{ backgroundColor: bg3 }} />
    </div>
  );

  return (
    <div className="flex h-full">
      {mode !== 'dark' && lightHalf}
      {mode === 'system' && <div className="w-px bg-neutral-200" />}
      {mode !== 'light' && darkHalf}
    </div>
  );
}

export function AppearanceTab(): React.ReactElement {
  const { scheme, setScheme, mode, setMode } = useTheme();
  const { locale, setLocale, t } = useI18n();

  const schemeKeys: Scheme[] = ['warm', 'cold', 'green', 'ember'];
  const modeKeys: ThemeMode[] = ['light', 'dark', 'system'];

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.appearance.title')} />

      <SettingsCard>
        <SectionCardHeader title={t('settings.language')} />
        <SettingsChoiceGroup<Locale>
          label={t('settings.language')}
          value={locale}
          onChange={setLocale}
          options={[
            { value: 'en', label: 'English' },
            { value: 'zh-CN', label: '简体中文' },
          ]}
        />
      </SettingsCard>

      <SettingsCard>
        <SectionCardHeader title={t('settings.appearance.theme')} />

        <SettingsChoiceGroup
          label={t('settings.appearance.theme')}
          value={mode}
          onChange={setMode}
          options={modeKeys.map((key) => ({
            value: key,
            label: t(`settings.appearance.modes.${key}`),
            preview: <ModePreview mode={key} scheme={scheme} />,
          }))}
        />
      </SettingsCard>

      <SettingsCard>
        <SectionCardHeader title={t('settings.appearance.colorScheme')} />

        <SettingsChoiceGroup
          label={t('settings.appearance.colorScheme')}
          value={scheme}
          onChange={setScheme}
          options={schemeKeys.map((key) => ({
            value: key,
            label: t(`settings.appearance.schemes.${key}`),
            preview: <CardPreview s={key} />,
          }))}
        />
      </SettingsCard>
    </SettingsPage>
  );
}
