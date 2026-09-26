import React, { useRef, useState } from 'react';
import { ArrowDownTrayIcon, FilmIcon, PlayIcon } from '@heroicons/react/24/outline';
import { BrutalButton, BrutalLink } from '../BrutalButton';
import { useI18n } from '../../i18n';

export function VideoResultPlayer({
  src,
  path,
}: {
  src: string;
  path: string;
}): React.ReactElement {
  const { t } = useI18n();
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playBlocked, setPlayBlocked] = useState(false);
  const [ratio, setRatio] = useState(16 / 9);
  const [resolution, setResolution] = useState('');
  const filename = path.split(/[\\/]/).pop() || path;
  return (
    <figure
      className="my-2 w-full overflow-hidden border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800"
      style={{ maxWidth: `min(100%, ${Math.min(672, 448 * ratio)}px)` }}
    >
      <div className="flex items-center justify-between gap-3 border-b-2 border-brutal-black px-3 py-2 dark:text-white">
        <span className="flex min-w-0 items-center gap-2 text-xs font-black uppercase tracking-wide">
          <FilmIcon className="h-4 w-4 shrink-0" />
          {t('videoPlayer.title')}
        </span>
        {resolution && (
          <span className="shrink-0 font-mono text-[10px] text-neutral-500">{resolution}</span>
        )}
      </div>
      <div className="relative bg-black" style={{ aspectRatio: ratio, maxHeight: '28rem' }}>
        <video
          ref={video}
          src={src}
          controls
          playsInline
          preload="metadata"
          aria-label={t('videoPlayer.title')}
          className="h-full w-full object-contain"
          onLoadedMetadata={(event) => {
            const element = event.currentTarget;
            if (element.videoWidth && element.videoHeight) {
              setRatio(element.videoWidth / element.videoHeight);
              setResolution(`${element.videoWidth} × ${element.videoHeight}`);
            }
          }}
          onPlay={() => {
            setPlaying(true);
            setPlayBlocked(false);
          }}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={() => {
            setFailed(true);
            setPlaying(false);
          }}
        />
        {!playing && !failed && (
          <BrutalButton
            size="icon-lg"
            variant="primary"
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            aria-label={t('speech.play')}
            onClick={() => {
              void video.current?.play().catch(() => setPlayBlocked(true));
            }}
          >
            <PlayIcon className="h-5 w-5" />
          </BrutalButton>
        )}
        {failed && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-neutral-950 p-4 text-center text-sm text-white">
            <p role="alert">{t('videoPlayer.failed')}</p>
            <BrutalButton
              size="sm"
              onClick={() => {
                setFailed(false);
                setPlayBlocked(false);
                video.current?.load();
              }}
            >
              {t('videoPlayer.retry')}
            </BrutalButton>
          </div>
        )}
      </div>
      <figcaption className="flex items-center justify-between gap-3 border-t-2 border-brutal-black px-3 py-2 dark:text-white">
        <span className="min-w-0 truncate font-mono text-[11px] text-neutral-500" title={filename}>
          {filename}
        </span>
        <BrutalLink
          href={src}
          download={filename}
          size="icon"
          aria-label={t('videoPlayer.download')}
          title={t('videoPlayer.download')}
        >
          <ArrowDownTrayIcon className="h-4 w-4" />
        </BrutalLink>
      </figcaption>
      {playBlocked && (
        <p role="status" className="px-3 pb-2 text-xs text-neutral-500">
          {t('speech.playbackBlocked')}
        </p>
      )}
    </figure>
  );
}
