import React from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { latestLines, type VoiceSession } from '../../hooks/useVoiceSession';
import { VoiceCubeStage } from './VoiceCubeStage';

interface VoiceBarProps {
  voice: Pick<
    VoiceSession,
    'status' | 'transcripts' | 'working' | 'liveCaptions' | 'errorKey' | 'stop' | 'interrupt'
  > &
    Partial<Pick<VoiceSession, 'micLevel'>>;
}

const WAVE_WEIGHTS = [0.32, 0.58, 0.85, 1.0, 1.0, 0.85, 0.58, 0.32];

/**
 * Center-aligned symmetric voice waveform. At silence it rests as a uniform
 * row of 2px micro-ticks; when the mic hears speech it expands symmetrically
 * from the midline without re-rendering React.
 */
const MicMeter: React.FC<{ level: { readonly current: number } }> = ({ level }) => {
  const barsRef = React.useRef<HTMLSpanElement>(null);
  React.useEffect(() => {
    let frame = 0;
    let shown = 0;
    const draw = (now: number) => {
      const target = level.current;
      shown += (target - shown) * (target > shown ? 0.6 : 0.14);
      const bars = barsRef.current?.children;
      if (bars) {
        const t = now / 1000;
        for (let i = 0; i < bars.length; i += 1) {
          const flutter = shown > 0.03 ? 0.82 + 0.18 * Math.sin(t * 16 + i * 1.1) : 1;
          const amp = Math.min(1, shown * WAVE_WEIGHTS[i] * flutter * 1.35);
          const scaleY = 0.16 + 0.84 * amp;
          const opacity = 0.28 + 0.72 * Math.min(1, shown * 1.8);
          const el = bars[i] as HTMLElement;
          el.style.transform = `scaleY(${scaleY.toFixed(3)})`;
          el.style.opacity = opacity.toFixed(2);
        }
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [level]);
  return (
    <span
      ref={barsRef}
      data-testid="mic-meter"
      aria-hidden
      className="flex h-3 items-center gap-[2px] px-0.5"
    >
      {WAVE_WEIGHTS.map((_, i) => (
        <span
          key={i}
          className="h-full w-[2px] origin-center bg-brutal-black dark:bg-white"
          style={{ transform: 'scaleY(0.16)', opacity: 0.28 }}
        />
      ))}
    </span>
  );
};

/**
 * Flush upper voice stage of the composer card: call status, Liquid-Geo 3D
 * voxel monolith, and live captions of the latest exchange.
 */
export const VoiceBar: React.FC<VoiceBarProps> = ({ voice }) => {
  const { t } = useI18n();
  if (voice.status === 'idle') return null;

  const failed = voice.status === 'error';
  const { user, assistant } = latestLines(voice.transcripts);
  const waitingForWords =
    voice.status === 'user_speaking' && voice.liveCaptions === false && !(user && !user.final);
  const live = voice.status === 'user_speaking' || voice.status === 'speaking';

  return (
    <section
      aria-label={t('voice.micButton')}
      className="-mx-1.5 -mt-1.5 mb-1 border-b-2 border-brutal-black bg-neutral-50/40 text-xs text-brutal-black dark:border-zinc-600 dark:bg-zinc-900/60 dark:text-white"
    >
      <header className="flex items-center gap-2 px-3 pt-2 pb-0.5">
        <span
          aria-hidden
          className={`h-2 w-2 shrink-0 ${
            failed
              ? 'border border-brutal-black bg-transparent dark:border-white'
              : `bg-brutal-black dark:bg-white ${live ? 'animate-pulse' : ''}`
          }`}
        />
        <strong className="tracking-wider uppercase" role="status" aria-live="polite">
          {failed
            ? t(voice.errorKey ?? 'voice.errors.session_error')
            : t(`voice.states.${voice.status}`)}
        </strong>
        {!failed && voice.status !== 'connecting' && voice.micLevel && (
          <MicMeter level={voice.micLevel} />
        )}
        {voice.working && !failed && (
          <span className="border border-brutal-black px-1.5 py-px font-bold dark:border-white">
            {t('voice.working')}
          </span>
        )}
        <div className="min-w-0 flex-1" />
        {voice.status === 'speaking' && (
          <button
            type="button"
            className="border border-brutal-black bg-white px-2 py-0.5 font-bold uppercase hover:bg-brutal-black hover:text-white dark:border-white dark:bg-zinc-800 dark:hover:bg-white dark:hover:text-brutal-black"
            onClick={voice.interrupt}
          >
            {t('voice.stopSpeaking')}
          </button>
        )}
        <button
          type="button"
          onClick={voice.stop}
          aria-label={t('voice.end')}
          title={t('voice.end')}
          className="flex h-5 w-5 items-center justify-center hover:opacity-60"
        >
          <XMarkIcon className="h-4 w-4" />
        </button>
      </header>
      <VoiceCubeStage status={voice.status} working={voice.working} micLevel={voice.micLevel} />
      {!failed && (user || assistant || waitingForWords) && (
        <dl className="space-y-0.5 border-t border-brutal-black/15 px-3 py-1.5 dark:border-white/15">
          {(user || waitingForWords) && (
            <div className="flex gap-2">
              <dt className="w-12 shrink-0 font-bold uppercase">{t('voice.transcript.you')}</dt>
              <dd
                className={`line-clamp-2 min-w-0 flex-1 break-words ${
                  user && user.final && !waitingForWords
                    ? ''
                    : 'text-neutral-500 dark:text-neutral-400'
                }`}
              >
                {waitingForWords ? t('voice.captionsAfterSpeech') : user?.text}
              </dd>
            </div>
          )}
          {assistant && (
            <div className="flex gap-2">
              <dt className="w-12 shrink-0 font-bold uppercase">
                {t('voice.transcript.assistant')}
              </dt>
              <dd
                className={`line-clamp-2 min-w-0 flex-1 break-words ${
                  assistant.final ? '' : 'text-neutral-500 dark:text-neutral-400'
                }`}
              >
                {assistant.text}
              </dd>
            </div>
          )}
        </dl>
      )}
    </section>
  );
};
