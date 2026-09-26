import { SpeakerWaveIcon } from '@heroicons/react/24/outline';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalOnOff } from '../BrutalOnOff';
import { SettingsCard, SectionCardHeader } from './SettingsCard';
import { ModelDropdown } from './ModelRolesTab';
import { resetSpeechForModel, speechModelOptions } from './speechModels';
import { speechQueue } from '../../lib/speechPlayback';
import React, { useEffect, useState } from 'react';
import { getApiBase } from '../../lib/api';
import { useI18n } from '../../i18n';
import { useSystemVoices } from '../chat/SpeechPlayer';
import { BrutalButton } from '../BrutalButton';

interface VoiceSettings {
  autoplay: boolean;
  engine: 'system' | 'api';
  voice: string;
  speed: number;
  pitch: number;
  volume: number;
  language: string;
  response_format: string;
  instructions: string;
}

export function VoiceSettingsCard({
  suggestions = [],
  unregisteredModels = [],
  onModelsSaved,
}: {
  suggestions?: string[];
  unregisteredModels?: string[];
  onModelsSaved?: (models: string[]) => void;
}): React.ReactElement {
  const [models, setModels] = useState<string[]>([]);
  const [customVoice, setCustomVoice] = useState(false);
  const [modelChanged, setModelChanged] = useState(false);
  const modelOptions = speechModelOptions(models[0] || '');
  const { t } = useI18n();
  const voices = useSystemVoices();
  const [settings, setSettings] = useState<VoiceSettings | null>(null);
  const [status, setStatus] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void fetch(`${getApiBase()}/config/voice`)
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const { tts_models = [], ...data } = (await response.json()) as VoiceSettings & {
          tts_models?: string[];
        };
        if (!cancelled) {
          const compatible =
            data.engine === 'api'
              ? { ...resetSpeechForModel(data, tts_models[0] || ''), voice: data.voice }
              : data;
          setSettings(compatible);
          setModelChanged(
            compatible.speed !== data.speed ||
              compatible.response_format !== data.response_format ||
              compatible.instructions !== data.instructions
          );
          setModels(tts_models);
          setCustomVoice(
            !!data.voice && !speechModelOptions(tts_models[0] || '').voices.includes(data.voice)
          );
        }
      })
      .catch(() => {
        if (!cancelled) setStatus('speech.failed');
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const update = (patch: Partial<VoiceSettings>) => {
    setSettings((value) => (value ? { ...value, ...patch } : value));
    setStatus('');
  };
  const save = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${getApiBase()}/config/voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...settings, tts_models: models }),
      });
      if (!response.ok) throw new Error();
      speechQueue.setAutoplay(settings?.autoplay !== false);
      onModelsSaved?.(models);
      setModelChanged(false);
      setStatus('speech.saved');
    } catch {
      setStatus('speech.failed');
    } finally {
      setSaving(false);
    }
  };
  const fieldClass =
    'mt-1 block w-full border-2 border-brutal-black bg-white px-3 py-2 text-sm font-normal dark:bg-zinc-800 focus:outline-none focus:border-brutal-blue';
  return (
    <SettingsCard className="space-y-4">
      <SectionCardHeader
        title={t('speech.controls')}
        icon={<SpeakerWaveIcon className="h-5 w-5" />}
        iconTone="blue"
      />
      {settings && (
        <fieldset
          disabled={saving}
          className="grid grid-cols-1 gap-4 text-sm font-medium sm:grid-cols-2"
        >
          <label className="flex items-center justify-between gap-4 border-b border-neutral-200 pb-4 text-xs font-bold uppercase tracking-wide dark:border-zinc-700 sm:col-span-2">
            {t('speech.autoplay')}
            <BrutalOnOff
              checked={settings.autoplay !== false}
              disabled={saving}
              onChange={(autoplay) => update({ autoplay })}
            />
          </label>
          <label className="block">
            {t('speech.engine')}
            <BrutalSelect
              className="mt-1"
              disabled={saving}
              value={settings.engine}
              options={[
                { value: 'system', label: t('speech.system') },
                { value: 'api', label: t('speech.api') },
              ]}
              onChange={(engine) => {
                setCustomVoice(false);
                update(
                  engine === 'api'
                    ? { ...resetSpeechForModel(settings, models[0] || ''), engine: 'api' }
                    : { engine: 'system', voice: '' }
                );
              }}
            />
          </label>
          {settings.engine === 'api' && (
            <div className="sm:col-span-2 space-y-2">
              <label className="block">{t('speech.model')}</label>
              <ModelDropdown
                label={models[0] || t('settings.roles.chooseModel')}
                options={[...new Set([...suggestions, ...unregisteredModels])]}
                unregisteredModels={new Set(unregisteredModels)}
                onSelect={(model) => {
                  if (model === models[0]) return;
                  setModels([model, ...models.slice(1).filter((id) => id !== model)]);
                  update(resetSpeechForModel(settings, model));
                  setCustomVoice(false);
                  setModelChanged(true);
                }}
              />
              {models.length > 0 && (
                <BrutalButton
                  size="xs"
                  onClick={() => {
                    setModels([]);
                    update({ voice: '' });
                    setCustomVoice(false);
                    setModelChanged(true);
                  }}
                >
                  {t('settings.roles.clearRole')}
                </BrutalButton>
              )}
              {modelChanged && (
                <p role="status" className="text-xs text-neutral-500">
                  {t('speech.modelChanged')}
                </p>
              )}
              {models.length > 1 && (
                <p className="text-xs text-neutral-500">
                  {t('speech.savedBackups', { count: models.length - 1 })}
                </p>
              )}
            </div>
          )}
          {settings.engine === 'system' ? (
            <>
              <p className="text-xs font-normal leading-relaxed text-neutral-500 sm:col-span-2">
                {t('speech.systemHelp')}
              </p>
              <label className="block">
                {t('speech.voice')}
                <BrutalSelect
                  className="mt-1"
                  disabled={saving}
                  value={settings.voice}
                  onChange={(voice) => update({ voice })}
                  options={[
                    { value: '', label: t('speech.defaultVoice') },
                    ...(settings.voice && !voices.some((voice) => voice.voiceURI === settings.voice)
                      ? [{ value: settings.voice, label: settings.voice }]
                      : []),
                    ...voices.map((voice) => ({
                      value: voice.voiceURI,
                      label: `${voice.name} (${voice.lang})`,
                    })),
                  ]}
                />
              </label>
              {!voices.length && <p role="status">{t('speech.unavailable')}</p>}
              <label className="block">
                {t('speech.language')}
                <input
                  className={fieldClass}
                  value={settings.language}
                  maxLength={40}
                  onChange={(e) => update({ language: e.target.value })}
                />
              </label>
            </>
          ) : (
            <>
              <p className="text-xs font-normal leading-relaxed text-neutral-500 sm:col-span-2">
                {t('speech.apiHelp')}
              </p>
              <label className="block">
                {t('speech.voice')}
                {modelOptions.voices.length > 0 && (
                  <BrutalSelect
                    className="mt-1"
                    disabled={saving}
                    value={customVoice ? '__custom__' : settings.voice}
                    onChange={(value) => {
                      setCustomVoice(value === '__custom__');
                      update({ voice: value === '__custom__' ? '' : value });
                    }}
                    options={[
                      { value: '', label: t('speech.providerDefault') },
                      ...modelOptions.voices.map((voice) => ({ value: voice, label: voice })),
                      { value: '__custom__', label: t('speech.customVoice') },
                    ]}
                  />
                )}
                {(customVoice || !modelOptions.voices.length) && (
                  <input
                    aria-label={t('speech.customVoice')}
                    className={fieldClass}
                    value={settings.voice}
                    maxLength={200}
                    onChange={(event) => update({ voice: event.target.value })}
                  />
                )}
              </label>
              <label className="block">
                {t('speech.format')}
                <BrutalSelect
                  className="mt-1"
                  disabled={saving}
                  value={settings.response_format}
                  onChange={(response_format) => update({ response_format })}
                  options={modelOptions.formats.map((format) => ({
                    value: format,
                    label: format === 'auto' ? t('speech.autoFormat') : format.toUpperCase(),
                  }))}
                />
              </label>
              {modelOptions.instructions && (
                <label className="block sm:col-span-2">
                  {t('speech.instructions')}
                  <textarea
                    className={fieldClass}
                    value={settings.instructions}
                    rows={3}
                    maxLength={4000}
                    onChange={(e) => update({ instructions: e.target.value })}
                  />
                </label>
              )}
            </>
          )}
          {(
            [
              ...(settings.engine === 'system' || modelOptions.speed ? ['speed'] : []),
              ...(settings.engine === 'system' ? ['pitch'] : []),
              'volume',
            ] as ('speed' | 'pitch' | 'volume')[]
          ).map((key) => (
            <label
              className="block border-t border-neutral-200 pt-4 dark:border-zinc-700"
              key={key}
            >
              <span className="mb-3 flex items-center justify-between gap-2 text-xs font-bold uppercase tracking-wide">
                {t(`speech.${key}`)}
                <output className="border-2 border-brutal-black bg-neutral-50 px-2 py-0.5 font-mono tabular-nums dark:bg-zinc-900">
                  {key === 'volume'
                    ? `${Math.round(settings[key] * 100)}%`
                    : `${settings[key].toFixed(2)}×`}
                </output>
              </span>
              <input
                className="block w-full cursor-pointer accent-brutal-blue focus-visible:outline-2 focus-visible:outline-brutal-blue"
                type="range"
                min={key === 'speed' ? 0.25 : 0}
                max={key === 'speed' ? 4 : key === 'pitch' ? 2 : 1}
                step={0.05}
                value={settings[key]}
                onChange={(e) => update({ [key]: Number(e.target.value) })}
              />
            </label>
          ))}
          <BrutalButton
            className="justify-self-end sm:col-span-2"
            onClick={() => void save()}
            disabled={saving}
          >
            {t('common.save')}
          </BrutalButton>
        </fieldset>
      )}
      {status && <p role="status">{t(status)}</p>}
    </SettingsCard>
  );
}
