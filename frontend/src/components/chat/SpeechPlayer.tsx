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
  const id = speechId(metadata, src);
  const state = useSyncExternalStore(
    speechQueue.subscribe,
    () => speechQueue.state(id),
    () => 'idle'
  );
  const busy = state === 'playing' || state === 'queued';
  const unavailable = !src && !voices.length;
  const status = busy
    ? t(state === 'queued' ? 'speech.queued' : 'speech.playing')
    : t('speech.clip');
  return (
    <div className="my-2 w-fit max-w-full">
      <button
        type="button"
        aria-label={t(busy ? 'speech.stop' : 'speech.play')}
        disabled={unavailable}
        onClick={() => {
          if (busy) {
            speechQueue.stop(id);
          } else {
            const job = createSpeechJob(metadata, src);
            speechQueue.enqueue({ ...job, id });
          }
        }}
        className={`flex h-11 w-44 max-w-full items-center gap-3 border px-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
          busy
            ? 'border-brutal-blue bg-brutal-blue text-white'
            : 'border-neutral-300 bg-neutral-100 text-brutal-black hover:bg-neutral-200 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700'
        }`}
      >
        <span
          aria-hidden="true"
          className={`flex h-5 w-12 shrink-0 items-center justify-center gap-[3px] ${state === 'playing' ? 'speech-wave-playing' : ''}`}
        >
          {[6, 12, 8, 16, 10, 14, 7].map((height, index) => (
            <span
              key={`${index}-${height}`}
              className={`w-0.5 bg-current ${state === 'playing' ? '' : 'opacity-55'}`}
              style={{ height: `${height}px`, animationDelay: `${index * 70}ms` }}
            />
          ))}
        </span>
        <span role="status" className="min-w-0 flex-1 truncate text-xs font-semibold">
          {status}
        </span>
      </button>
      {unavailable && (
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
