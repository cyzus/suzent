import React, { useState } from 'react';
import {
  useTheme,
  SCHEME_COLORS,
  SCHEME_SURFACES,
  type Scheme,
  type ThemeMode,
} from '../../hooks/useTheme';
import {
  CHAT_FONT_SIZE_OPTIONS,
  CHAT_WIDTH_OPTIONS,
  MOTION_OPTIONS,
  REPLY_FONT_OPTIONS,
  UI_FONT_OPTIONS,
  isLocalFontPickerSupported,
  queryAvailableLocalFonts,
  useAppearancePreferences,
  type ChatFontSize,
  type ChatWidth,
  type MotionMode,
  type ReplyFontPreset,
  type UiFontPreset,
} from '../../lib/appearancePreferences';
import { useI18n, type Locale } from '../../i18n';
import { BrutalSelect } from '../BrutalSelect';
import { SettingsChoiceGroup } from './SettingsChoiceGroup';
import { SettingsHeader } from './SettingsHeader';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';

const LOCAL_FONT_ACTION_VALUE = '__choose_local_font__';
const LOCAL_FONT_PREFIX = 'local:';

const ROW_SELECT_BUTTON_CLASS =
  '!w-auto !px-2 !py-1 !gap-1.5 !font-normal !text-sm !normal-case !text-neutral-700 dark:!text-neutral-200 hover:!bg-neutral-100 dark:hover:!bg-zinc-700 [&>svg]:!w-3.5 [&>svg]:!h-3.5 [&>svg]:!stroke-2 [&>svg]:text-neutral-500 dark:[&>svg]:text-neutral-400';

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

interface AppearanceRowProps {
  label: string;
  children: React.ReactNode;
}

function AppearanceRow({ label, children }: AppearanceRowProps): React.ReactElement {
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <span className="text-sm font-medium text-brutal-black dark:text-white">{label}</span>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function AppearanceTab(): React.ReactElement {
  const { scheme, setScheme, mode, setMode } = useTheme();
  const { locale, setLocale, t } = useI18n();
  const { preferences, setUiFont, setReplyFont, setChatFontSize, setChatWidth, setMotion } =
    useAppearancePreferences();

  const [localFonts, setLocalFonts] = useState<string[] | null>(null);
  const [loadingLocalFonts, setLoadingLocalFonts] = useState(false);
  const canQueryLocalFonts = isLocalFontPickerSupported();

  const schemeKeys: Scheme[] = ['warm', 'cold', 'green', 'ember'];
  const modeKeys: ThemeMode[] = ['light', 'dark', 'system'];

  const presetOptions = UI_FONT_OPTIONS.map((key) => ({
    value: key,
    label: t(`settings.appearance.uiFonts.${key}`),
    group:
      localFonts && localFonts.length > 0
        ? t('settings.appearance.uiFonts.presetGroup')
        : undefined,
  }));

  const currentCustomFont = preferences.customUiFontFamily;
  const activeUiFontValue = currentCustomFont
    ? `${LOCAL_FONT_PREFIX}${currentCustomFont}`
    : preferences.uiFont;

  const uiFontSelectedLabel = currentCustomFont
    ? `${currentCustomFont} · ${t(`settings.appearance.uiFonts.${preferences.uiFont}`)}`
    : t(`settings.appearance.uiFonts.${preferences.uiFont}`);

  const localFontOptions =
    localFonts && localFonts.length > 0
      ? localFonts.map((family) => ({
          value: `${LOCAL_FONT_PREFIX}${family}`,
          label: family,
          group: t('settings.appearance.uiFonts.localGroup'),
        }))
      : currentCustomFont
        ? [
            {
              value: `${LOCAL_FONT_PREFIX}${currentCustomFont}`,
              label: currentCustomFont,
              group: t('settings.appearance.uiFonts.localGroup'),
            },
          ]
        : [];

  const uiFontOptions = [
    ...presetOptions,
    ...localFontOptions,
    ...(canQueryLocalFonts && localFonts === null
      ? [
          {
            value: LOCAL_FONT_ACTION_VALUE,
            label: t('settings.appearance.uiFonts.chooseLocal'),
            disabled: loadingLocalFonts,
          },
        ]
      : []),
  ];

  async function handleLoadLocalFonts(): Promise<void> {
    if (loadingLocalFonts) return;
    setLoadingLocalFonts(true);
    try {
      const families = await queryAvailableLocalFonts();
      setLocalFonts(families);
    } catch {
      setLocalFonts([]);
    } finally {
      setLoadingLocalFonts(false);
    }
  }

  function handleUiFontChange(value: string): void {
    if (value === LOCAL_FONT_ACTION_VALUE) {
      void handleLoadLocalFonts();
      return;
    }
    if (value.startsWith(LOCAL_FONT_PREFIX)) {
      const family = value.slice(LOCAL_FONT_PREFIX.length);
      setUiFont(preferences.uiFont, family);
      return;
    }
    setUiFont(value as UiFontPreset, null);
  }

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

      <SettingsCard>
        <div className="divide-y divide-neutral-200 dark:divide-zinc-700">
          <AppearanceRow label={t('settings.appearance.uiFont')}>
            <BrutalSelect
              ariaLabel={t('settings.appearance.uiFont')}
              value={activeUiFontValue}
              selectedLabel={uiFontSelectedLabel}
              menuAlign="end"
              variant="ghost"
              buttonClassName={ROW_SELECT_BUTTON_CLASS}
              dropdownClassName="min-w-[200px] [&_button]:!normal-case"
              keepOpenOnSelect={(val) => val === LOCAL_FONT_ACTION_VALUE}
              onChange={handleUiFontChange}
              options={uiFontOptions}
            />
          </AppearanceRow>

          <AppearanceRow label={t('settings.appearance.replyFont')}>
            <BrutalSelect
              ariaLabel={t('settings.appearance.replyFont')}
              value={preferences.replyFont}
              menuAlign="end"
              variant="ghost"
              buttonClassName={ROW_SELECT_BUTTON_CLASS}
              dropdownClassName="min-w-[160px] [&_button]:!normal-case"
              onChange={(val) => setReplyFont(val as ReplyFontPreset)}
              options={REPLY_FONT_OPTIONS.map((key) => ({
                value: key,
                label: t(`settings.appearance.replyFonts.${key}`),
              }))}
            />
          </AppearanceRow>

          <AppearanceRow label={t('settings.appearance.chatFontSize')}>
            <BrutalSelect
              ariaLabel={t('settings.appearance.chatFontSize')}
              value={preferences.chatFontSize}
              menuAlign="end"
              variant="ghost"
              buttonClassName={ROW_SELECT_BUTTON_CLASS}
              dropdownClassName="min-w-[140px] [&_button]:!normal-case"
              onChange={(val) => setChatFontSize(val as ChatFontSize)}
              options={CHAT_FONT_SIZE_OPTIONS.map((key) => ({
                value: key,
                label: t(`settings.appearance.chatFontSizes.${key}`),
              }))}
            />
          </AppearanceRow>

          <AppearanceRow label={t('settings.appearance.chatWidth')}>
            <BrutalSelect
              ariaLabel={t('settings.appearance.chatWidth')}
              value={preferences.chatWidth}
              menuAlign="end"
              variant="ghost"
              buttonClassName={ROW_SELECT_BUTTON_CLASS}
              dropdownClassName="min-w-[140px] [&_button]:!normal-case"
              onChange={(val) => setChatWidth(val as ChatWidth)}
              options={CHAT_WIDTH_OPTIONS.map((key) => ({
                value: key,
                label: t(`settings.appearance.chatWidths.${key}`),
              }))}
            />
          </AppearanceRow>

          <AppearanceRow label={t('settings.appearance.motion')}>
            <BrutalSelect
              ariaLabel={t('settings.appearance.motion')}
              value={preferences.motion}
              menuAlign="end"
              variant="ghost"
              buttonClassName={ROW_SELECT_BUTTON_CLASS}
              dropdownClassName="min-w-[150px] [&_button]:!normal-case"
              onChange={(val) => setMotion(val as MotionMode)}
              options={MOTION_OPTIONS.map((key) => ({
                value: key,
                label: t(`settings.appearance.motions.${key}`),
              }))}
            />
          </AppearanceRow>
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
