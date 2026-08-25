import React from 'react';
import { useTheme, SCHEME_COLORS, SCHEME_SURFACES, type Scheme } from '../../hooks/useTheme';
import { useI18n, type Locale } from '../../i18n';
import { BrutalSelect } from '../BrutalSelect';
import { SettingsHeader } from './SettingsHeader';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';

/** Mini split preview: left = light half, right = dark half */
function CardPreview({ s }: { s: Scheme }) {
  const { light, dark } = SCHEME_COLORS[s];
  const { bg1: _bg1, bg2, bg3 } = SCHEME_SURFACES[s];

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

export function AppearanceTab(): React.ReactElement {
  const { scheme, setScheme } = useTheme();
  const { locale, setLocale, t } = useI18n();

  const schemeKeys: Scheme[] = ['warm', 'cold', 'green'];

  return (
    <SettingsPage>
      <SettingsHeader
        title={t('settings.appearance.title')}
        subtitle={t('settings.appearance.subtitle')}
      />

      <SettingsCard>
        <SectionCardHeader
          title={t('settings.language')}
          description={t('settings.appearance.languageDesc')}
        />
        <BrutalSelect
          value={locale}
          onChange={(value) => setLocale(value as Locale)}
          options={[
            { value: 'en', label: 'English' },
            { value: 'zh-CN', label: '简体中文' },
          ]}
          className="max-w-sm"
        />
      </SettingsCard>

      <SettingsCard>
        <SectionCardHeader
          title={t('settings.appearance.colorScheme')}
          description={t('settings.appearance.colorSchemeDesc')}
        />

        <div className="flex gap-5 flex-wrap">
          {schemeKeys.map((key) => {
            const isActive = scheme === key;

            return (
              <button
                key={key}
                onClick={() => setScheme(key)}
                className="flex flex-col items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-black focus-visible:ring-offset-2"
              >
                {/* Card */}
                <div
                  className={[
                    'w-40 h-28 border-3 border-brutal-black overflow-hidden transition-all',
                    isActive
                      ? 'shadow-brutal ring-[3px] ring-black ring-offset-2 ring-offset-white dark:ring-white dark:ring-offset-zinc-800'
                      : 'shadow-brutal hover:brightness-[0.98]',
                  ].join(' ')}
                >
                  <CardPreview s={key} />
                </div>

                {/* Label + checkmark */}
                <div className="flex items-center gap-1.5">
                  {isActive && (
                    <svg
                      className="w-3 h-3 text-brutal-black dark:text-white flex-shrink-0"
                      fill="currentColor"
                      viewBox="0 0 12 12"
                    >
                      <path d="M10 3L5 8.5 2 5.5 1 6.5l4 4 6-7z" />
                    </svg>
                  )}
                  <span
                    className={`text-xs font-bold uppercase ${
                      isActive
                        ? 'text-brutal-black dark:text-white'
                        : 'text-neutral-400 dark:text-neutral-500'
                    }`}
                  >
                    {t(`settings.appearance.schemes.${key}` as any)}
                  </span>
                </div>

                {/* Accent swatches: light + dark */}
                <div className="flex gap-1">
                  <div
                    className="w-4 h-4 border-2 border-brutal-black"
                    title="Light accent"
                    style={{ backgroundColor: SCHEME_COLORS[key].light }}
                  />
                  <div
                    className="w-4 h-4 border-2 border-brutal-black"
                    title="Dark accent"
                    style={{ backgroundColor: SCHEME_COLORS[key].dark }}
                  />
                </div>
              </button>
            );
          })}
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
