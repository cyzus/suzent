import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { PlayIcon, StopIcon, SpeakerWaveIcon } from '@heroicons/react/24/outline';
import { BrutalIconButton } from '../BrutalButton';
import { BrutalSelect } from '../BrutalSelect';
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
    <div className="my-2 w-full max-w-sm space-y-2 border border-neutral-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-800">
      <div className="flex items-center gap-3">
        <BrutalIconButton
          type="button"
          variant="primary"
          size="icon-lg"
          className="shrink-0 !border-0 !shadow-none"
          label={t(busy ? 'speech.stop' : 'speech.play')}
          disabled={!busy && !src && !voices.length}
          onClick={() => {
            if (busy) {
              speechQueue.stop(id);
            } else {
              const job = createSpeechJob({ ...metadata, voice: selected }, src);
              speechQueue.enqueue({ ...job, id });
            }
          }}
        >
          {busy ? <StopIcon className="h-4 w-4" /> : <PlayIcon className="h-4 w-4" />}
        </BrutalIconButton>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-brutal-black dark:text-white">
            {t('speech.clip')}
          </p>
          <p
            role="status"
            className={`h-4 truncate text-xs leading-4 ${busy ? 'text-brutal-blue' : 'text-neutral-500 dark:text-neutral-400'}`}
          >
            {busy
              ? t(state === 'queued' ? 'speech.queued' : 'speech.playing')
              : `${t(src ? 'speech.api' : 'speech.system')}${src && selected ? ` · ${selected}` : ''}`}
          </p>
        </div>
        <SpeakerWaveIcon
          aria-hidden="true"
          className={`h-5 w-5 shrink-0 ${state === 'playing' ? 'text-brutal-blue' : 'text-neutral-400'}`}
        />
      </div>
      {!src && (
        <BrutalSelect
          label={t('speech.voice')}
          value={selected}
          onChange={setSelected}
          disabled={busy}
          buttonClassName="!border !border-neutral-200 !shadow-none dark:!border-zinc-700"
          options={[
            { value: '', label: t('speech.defaultVoice') },
            ...voices.map((voice) => ({
              value: voice.voiceURI,
              label: `${voice.name} (${voice.lang})`,
            })),
          ]}
        />
      )}
      {!src && !voices.length && (
        <p role="status" className="text-xs text-neutral-500 dark:text-neutral-400">
          {t('speech.unavailable')}
        </p>
      )}
      {state === 'blocked' && (
        <p role="alert" className="text-xs text-brutal-red">
          {t('speech.playbackBlocked')}
        </p>
      )}
    </div>
  );
}
