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
  onOpenModelRoles,
}: {
  onOpenModelRoles?: () => void;
}): React.ReactElement {
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
        const data = (await response.json()) as VoiceSettings;
        if (!cancelled) setSettings(data);
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
        body: JSON.stringify(settings),
      });
      if (!response.ok) throw new Error();
      speechQueue.setAutoplay(settings?.autoplay !== false);
      setStatus('speech.saved');
    } catch {
      setStatus('speech.failed');
    } finally {
      setSaving(false);
    }
  };
  const fieldClass =
    'mt-1 block w-full border-2 border-brutal-black bg-white px-3 py-2 text-sm font-normal dark:bg-zinc-800';
  return (
    <section className="space-y-4 border-2 border-brutal-black bg-white p-4 shadow-brutal-sm dark:bg-zinc-800 dark:text-white sm:p-5">
      {onOpenModelRoles && (
        <BrutalButton size="sm" onClick={onOpenModelRoles}>
          {t('speech.openModels')}
        </BrutalButton>
      )}
      {settings && (
        <fieldset
          disabled={saving}
          className="grid grid-cols-1 gap-4 text-sm font-medium sm:grid-cols-2"
        >
          <label className="flex items-center gap-2 sm:col-span-2">
            <input
              type="checkbox"
              checked={settings.autoplay !== false}
              onChange={(event) => update({ autoplay: event.target.checked })}
            />
            {t('speech.autoplay')}
          </label>
          <label className="block">
            {t('speech.engine')}
            <select
              className={fieldClass}
              value={settings.engine}
              onChange={(e) =>
                update({ engine: e.target.value as VoiceSettings['engine'], voice: '' })
              }
            >
              <option value="system">{t('speech.system')}</option>
              <option value="api">{t('speech.api')}</option>
            </select>
          </label>
          {settings.engine === 'system' ? (
            <>
              <p className="text-xs font-normal leading-relaxed text-neutral-500 sm:col-span-2">
                {t('speech.systemHelp')}
              </p>
              <label className="block">
                {t('speech.voice')}
                <select
                  className={fieldClass}
                  value={settings.voice}
                  onChange={(e) => update({ voice: e.target.value })}
                >
                  <option value="">{t('speech.defaultVoice')}</option>
                  {settings.voice && !voices.some((voice) => voice.voiceURI === settings.voice) && (
                    <option value={settings.voice}>{settings.voice}</option>
                  )}
                  {voices.map((voice) => (
                    <option key={voice.voiceURI} value={voice.voiceURI}>
                      {voice.name} ({voice.lang})
                    </option>
                  ))}
                </select>
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
                <input
                  className={fieldClass}
                  value={settings.voice}
                  maxLength={200}
                  onChange={(e) => update({ voice: e.target.value })}
                />
              </label>
              <label className="block">
                {t('speech.format')}
                <select
                  className={fieldClass}
                  value={settings.response_format}
                  onChange={(e) => update({ response_format: e.target.value })}
                >
                  <option value="auto">{t('speech.autoFormat')}</option>
                  {['mp3', 'wav', 'opus', 'aac', 'flac'].map((format) => (
                    <option key={format}>{format}</option>
                  ))}
                </select>
              </label>
              <label className="block sm:col-span-2">
                {t('speech.instructions')}
                <textarea
                  className={fieldClass}
                  value={settings.instructions}
                  maxLength={4000}
                  onChange={(e) => update({ instructions: e.target.value })}
                />
              </label>
            </>
          )}
          {(
            ['speed', ...(settings.engine === 'system' ? ['pitch'] : []), 'volume'] as (
              'speed' | 'pitch' | 'volume'
            )[]
          ).map((key) => (
            <label className="block" key={key}>
              {t(`speech.${key}`)}: {settings[key]}
              <input
                className="block w-full"
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
    </section>
  );
}
