import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';

export function useSystemVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    if (!('speechSynthesis' in window)) return;
    const update = () =>
      setVoices(window.speechSynthesis.getVoices().filter((voice) => voice.localService));
    update();
    window.speechSynthesis.addEventListener('voiceschanged', update);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', update);
  }, []);
  return voices;
}

export function SpeechPlayer({
  metadata,
}: {
  metadata: Record<string, unknown>;
}): React.ReactElement {
  const { t } = useI18n();
  const voices = useSystemVoices();
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);
  const active = useRef<SpeechSynthesisUtterance | null>(null);
  const [selected, setSelected] = useState(String(metadata.voice || ''));
  useEffect(
    () => () => {
      if (active.current) {
        active.current.onend = null;
        active.current.onerror = null;
        window.speechSynthesis.cancel();
      }
    },
    []
  );
  const play = () => {
    const language = String(metadata.language || '');
    const voice =
      voices.find((item) => item.voiceURI === selected || item.name === selected) ||
      voices.find(
        (item) => language && item.lang.toLowerCase().startsWith(language.toLowerCase())
      ) ||
      voices.find((item) => item.default) ||
      voices[0];
    if (!voice) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(String(metadata.text || ''));
    utterance.voice = voice;
    utterance.lang = language || voice.lang;
    utterance.rate = Number(metadata.speed ?? 1);
    utterance.pitch = Number(metadata.pitch ?? 1);
    utterance.volume = Number(metadata.volume ?? 1);
    utterance.onend = () => {
      if (active.current !== utterance) return;
      setPlaying(false);
      active.current = null;
    };
    utterance.onerror = (event) => {
      if (active.current !== utterance) return;
      setPlaying(false);
      setError(event.error !== 'canceled' && event.error !== 'interrupted');
      active.current = null;
    };
    active.current = utterance;
    setError(false);
    setPlaying(true);
    window.speechSynthesis.speak(utterance);
  };
  return (
    <div className="space-y-2 border-2 border-brutal-black p-3">
      <p className="text-xs font-bold">{t('speech.system')}</p>
      <select
        aria-label={t('speech.voice')}
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="max-w-full bg-transparent"
      >
        <option value="">{t('speech.defaultVoice')}</option>
        {voices.map((voice) => (
          <option key={voice.voiceURI} value={voice.voiceURI}>
            {voice.name} ({voice.lang})
          </option>
        ))}
      </select>
      <div className="flex gap-3">
        <button type="button" disabled={!voices.length || playing} onClick={play}>
          {t('speech.play')}
        </button>
        <button
          type="button"
          disabled={!playing}
          onClick={() => {
            window.speechSynthesis.cancel();
            active.current = null;
            setPlaying(false);
          }}
        >
          {t('speech.stop')}
        </button>
      </div>
      {!voices.length && <p role="status">{t('speech.unavailable')}</p>}
      {error && <p role="alert">{t('speech.failed')}</p>}
    </div>
  );
}
