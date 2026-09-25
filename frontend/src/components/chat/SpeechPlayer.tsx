import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { useI18n } from '../../i18n';
import { createSpeechJob, speechId, speechQueue } from '../../lib/speechPlayback';

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
  src,
}: {
  metadata: Record<string, unknown>;
  src?: string;
}): React.ReactElement {
  const { t } = useI18n();
  const voices = useSystemVoices();
  const [selected, setSelected] = useState(String(metadata.voice || ''));
  const id = speechId(metadata, src);
  const state = useSyncExternalStore(
    speechQueue.subscribe,
    () => speechQueue.state(id),
    () => 'idle'
  );
  const busy = state === 'playing' || state === 'queued';
  return (
    <div className="space-y-2 border-2 border-brutal-black p-3">
      <p className="text-xs font-bold">{t(src ? 'speech.api' : 'speech.system')}</p>
      {!src && (
        <select
          aria-label={t('speech.voice')}
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          className="max-w-full bg-transparent"
        >
          <option value="">{t('speech.defaultVoice')}</option>
          {voices.map((voice) => (
            <option key={voice.voiceURI} value={voice.voiceURI}>
              {voice.name} ({voice.lang})
            </option>
          ))}
        </select>
      )}
      <div className="flex gap-3">
        <button
          type="button"
          disabled={(!src && !voices.length) || busy}
          onClick={() => {
            const job = createSpeechJob({ ...metadata, voice: selected }, src);
            speechQueue.enqueue({ ...job, id });
          }}
        >
          {t('speech.play')}
        </button>
        <button type="button" disabled={!busy} onClick={() => speechQueue.stop(id)}>
          {t('speech.stop')}
        </button>
      </div>
      {busy && <p role="status">{t(state === 'queued' ? 'speech.queued' : 'speech.playing')}</p>}
      {!src && !voices.length && <p role="status">{t('speech.unavailable')}</p>}
      {state === 'blocked' && <p role="alert">{t('speech.playbackBlocked')}</p>}
    </div>
  );
}
