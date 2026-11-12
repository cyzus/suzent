import { BrutalRange } from '../BrutalRange';
import { SettingsChoiceGroup } from './SettingsChoiceGroup';
import { SpeakerWaveIcon, MicrophoneIcon } from '@heroicons/react/24/outline';
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
import { VOICE_SETTINGS_EVENT } from '../../hooks/useWakeWord';

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
  realtime_model: string;
  realtime_voice: string;
  realtime_start_sensitivity?: 'auto' | 'low' | 'high';
  wake_word?: boolean;
  wake_phrases?: string[];
  wake_sensitivity?: number;
  voice_hotkey?: string;
}

interface WakeStatus {
  packages: boolean;
  model: boolean;
  unknown_words: string[];
}

/**
 * Make the wake word ready to listen: install the plugin's packages, then
 * the model, as far as either is missing. Returns an i18n key and params for
 * what is still wrong, or null when the wake word can listen.
 */
async function prepareWakeWord(
  onInstalling: () => void
): Promise<{ key: string; params?: Record<string, unknown> } | null> {
  const base = getApiBase();
  const read = async (response: Response): Promise<WakeStatus> => {
    if (!response.ok) throw new Error();
    return (await response.json()) as WakeStatus;
  };
  let status = await read(await fetch(`${base}/voice/wake`));
  if (!status.packages) {
    onInstalling();
    const installed = await fetch(`${base}/plugins/wake-word/install`, { method: 'POST' });
    if (!installed.ok) return { key: 'voice.wake.errors.install_failed' };
    status = await read(await fetch(`${base}/voice/wake`));
  }
  if (!status.model) {
    onInstalling();
    const downloaded = await fetch(`${base}/voice/wake/model`, { method: 'POST' });
    if (!downloaded.ok) return { key: 'voice.wake.errors.download_failed' };
    status = await read(downloaded);
  }
  if (!status.packages) return { key: 'voice.wake.errors.not_installed' };
  if (status.unknown_words.length)
    return {
      key: 'voice.wake.errors.unknown_words',
      params: { words: status.unknown_words.join(', ') },
    };
  return null;
}

interface RealtimeOption {
  id: string;
  label: string;
  configured: boolean;
  /** true: words stream while you speak; false: only after you finish; null: unmeasured. */
  live_captions?: boolean | null;
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
  const [realtimeOptions, setRealtimeOptions] = useState<RealtimeOption[]>([]);
  const [status, setStatus] = useState('');
  const [wakeProblem, setWakeProblem] = useState<{
    key: string;
    params?: Record<string, unknown>;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void fetch(`${getApiBase()}/config/voice`)
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const {
          tts_models = [],
          realtime_options = [],
          ...data
        } = (await response.json()) as VoiceSettings & {
          tts_models?: string[];
          realtime_options?: RealtimeOption[];
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
          setRealtimeOptions(realtime_options);
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
      setWakeProblem(null);
      if (settings?.wake_word) {
        setWakeProblem(
          await prepareWakeWord(() => setWakeProblem({ key: 'voice.wake.installing' })).catch(
            () => ({ key: 'voice.wake.errors.install_failed' })
          )
        );
      }
      // The chat window listens and registers the shortcut with these.
      window.dispatchEvent(
        new CustomEvent(VOICE_SETTINGS_EVENT, { detail: await response.json() })
      );
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
    <div className="space-y-4">
      <SettingsCard>
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
            <div className="sm:col-span-2">
              <SettingsChoiceGroup<'system' | 'api'>
                label={t('speech.engine')}
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
            </div>
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
                  <p role="status" className="text-xs text-neutral-500 dark:text-neutral-400">
                    {t('speech.modelChanged')}
                  </p>
                )}
                {models.length > 1 && (
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
                    {t('speech.savedBackups', { count: models.length - 1 })}
                  </p>
                )}
              </div>
            )}
            {settings.engine === 'system' ? (
              <>
                <p className="text-xs font-normal leading-relaxed text-neutral-500 dark:text-neutral-400 sm:col-span-2">
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
                      ...(settings.voice &&
                      !voices.some((voice) => voice.voiceURI === settings.voice)
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
                      rows={2}
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
              <BrutalRange
                key={key}
                label={t(`speech.${key}`)}
                value={settings[key]}
                valueText={
                  key === 'volume'
                    ? `${Math.round(settings[key] * 100)}%`
                    : `${settings[key].toFixed(2)}×`
                }
                min={key === 'speed' ? 0.25 : 0}
                max={key === 'speed' ? 4 : key === 'pitch' ? 2 : 1}
                step={0.05}
                disabled={saving}
                onChange={(value) => update({ [key]: value })}
              />
            ))}
          </fieldset>
        )}
      </SettingsCard>
      {settings && (
        <SettingsCard>
          <SectionCardHeader
            title={t('voice.settings.title')}
            icon={<MicrophoneIcon className="h-5 w-5" aria-hidden="true" />}
          />
          <fieldset
            disabled={saving}
            className="grid grid-cols-1 gap-4 text-sm font-medium sm:grid-cols-2"
          >
            <label className="block">
              {t('voice.settings.model')}
              <BrutalSelect
                className="mt-1"
                disabled={saving}
                value={settings.realtime_model}
                onChange={(realtime_model) => update({ realtime_model })}
                options={[
                  { value: '', label: t('voice.settings.auto') },
                  ...(settings.realtime_model &&
                  !realtimeOptions.some((option) => option.id === settings.realtime_model)
                    ? [
                        {
                          value: settings.realtime_model,
                          label: settings.realtime_model,
                          disabled: true,
                        },
                      ]
                    : []),
                  ...realtimeOptions.map((option) => ({
                    value: option.id,
                    label:
                      option.live_captions === false
                        ? `${option.label} · ${t('voice.settings.captionsAfterSpeech')}`
                        : option.label,
                    disabled: !option.configured,
                  })),
                ]}
              />
            </label>
            <label className="block">
              {t('voice.settings.voice')}
              <input
                className={fieldClass}
                value={settings.realtime_voice}
                maxLength={200}
                onChange={(event) => update({ realtime_voice: event.target.value })}
              />
            </label>
            {(!settings.realtime_model || settings.realtime_model.startsWith('gemini/')) && (
              <label className="block">
                {t('voice.settings.sensitivity')}
                <BrutalSelect
                  className="mt-1"
                  disabled={saving}
                  value={settings.realtime_start_sensitivity ?? 'low'}
                  onChange={(value) =>
                    update({
                      realtime_start_sensitivity:
                        value as VoiceSettings['realtime_start_sensitivity'],
                    })
                  }
                  options={[
                    { value: 'low', label: t('voice.settings.sensitivityLow') },
                    { value: 'auto', label: t('voice.settings.sensitivityAuto') },
                    { value: 'high', label: t('voice.settings.sensitivityHigh') },
                  ]}
                />
              </label>
            )}
            {!realtimeOptions.some((option) => option.configured) && (
              <p className="text-xs text-brutal-red">{t('voice.settings.noneConfigured')}</p>
            )}
          </fieldset>
        </SettingsCard>
      )}
      {settings && (
        <SettingsCard>
          <SectionCardHeader
            title={t('voice.wake.title')}
            icon={<MicrophoneIcon className="h-5 w-5" aria-hidden="true" />}
          />
          <fieldset
            disabled={saving}
            className="grid grid-cols-1 gap-4 text-sm font-medium sm:grid-cols-2"
          >
            <div className="space-y-1 border-b border-neutral-200 pb-4 dark:border-zinc-700 sm:col-span-2">
              <label className="flex items-center justify-between gap-4 text-xs font-bold uppercase tracking-wide">
                {t('voice.wake.enabled')}
                <BrutalOnOff
                  checked={!!settings.wake_word}
                  disabled={saving}
                  onChange={(wake_word) => update({ wake_word })}
                />
              </label>
              <p className="text-xs font-normal text-neutral-600 dark:text-neutral-400">
                {t('voice.wake.enabledHint')}
              </p>
            </div>
            {settings.wake_word && (
              <>
                <label className="block">
                  {t('voice.wake.phrases')}
                  <textarea
                    className={fieldClass}
                    rows={3}
                    value={(settings.wake_phrases ?? []).join('\n')}
                    onChange={(event) =>
                      update({ wake_phrases: event.target.value.split('\n').slice(0, 8) })
                    }
                  />
                  <span className="mt-1 block text-xs font-normal text-neutral-600 dark:text-neutral-400">
                    {t('voice.wake.phrasesHint')}
                  </span>
                </label>
                <div>
                  <BrutalRange
                    label={t('voice.wake.sensitivity')}
                    value={settings.wake_sensitivity ?? 0.5}
                    valueText={`${Math.round((settings.wake_sensitivity ?? 0.5) * 100)}%`}
                    min={0}
                    max={1}
                    step={0.05}
                    disabled={saving}
                    onChange={(wake_sensitivity) => update({ wake_sensitivity })}
                  />
                  <p className="mt-1 text-xs font-normal text-neutral-600 dark:text-neutral-400">
                    {t('voice.wake.sensitivityHint')}
                  </p>
                </div>
              </>
            )}
            <label className="block sm:col-span-2">
              {t('voice.wake.hotkey')}
              <input
                className={fieldClass}
                value={settings.voice_hotkey ?? ''}
                maxLength={60}
                placeholder="CommandOrControl+Shift+Space"
                onChange={(event) => update({ voice_hotkey: event.target.value.trim() })}
              />
              <span className="mt-1 block text-xs font-normal text-neutral-600 dark:text-neutral-400">
                {t('voice.wake.hotkeyHint')}
              </span>
            </label>
            {wakeProblem && (
              <p
                role="status"
                className={`text-xs sm:col-span-2 ${
                  wakeProblem.key === 'voice.wake.installing'
                    ? 'text-neutral-600 dark:text-neutral-400'
                    : 'text-brutal-red'
                }`}
              >
                {t(wakeProblem.key, wakeProblem.params)}
              </p>
            )}
          </fieldset>
        </SettingsCard>
      )}
      <div className="flex flex-wrap items-center justify-end gap-3">
        {status && (
          <p
            role="status"
            className={
              status === 'speech.failed'
                ? 'text-sm text-red-600 dark:text-red-400'
                : 'text-sm text-neutral-600 dark:text-neutral-400'
            }
          >
            {t(status)}
          </p>
        )}
        {settings && (
          <BrutalButton variant="primary" onClick={() => void save()} disabled={saving}>
            {t('common.save')}
          </BrutalButton>
        )}
      </div>
    </div>
  );
}
