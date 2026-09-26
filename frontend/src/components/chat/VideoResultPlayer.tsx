import React, { useRef, useState } from 'react';
import { PlayIcon } from '@heroicons/react/24/outline';
import { BrutalButton, BrutalIconButton } from '../BrutalButton';
import { VideoContextMenu } from './VideoContextMenu';
import { useI18n } from '../../i18n';

export function VideoResultPlayer({ src }: { src: string; path: string }): React.ReactElement {
  const { t } = useI18n();
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playBlocked, setPlayBlocked] = useState(false);
  const [ratio, setRatio] = useState(16 / 9);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  return (
    <figure
      className="my-2 w-full overflow-hidden border border-neutral-200 bg-white dark:border-zinc-700 dark:bg-zinc-800"
      onContextMenu={(event) => {
        event.preventDefault();
        setMenu({ x: event.clientX, y: event.clientY });
      }}
      onKeyDown={(event) => {
        if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
          event.preventDefault();
          const rect = event.currentTarget.getBoundingClientRect();
          setMenu({ x: rect.left + 12, y: rect.top + 12 });
        }
      }}
      style={{ maxWidth: `min(100%, ${Math.min(672, 448 * ratio)}px)` }}
    >
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
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <BrutalIconButton
              size="icon-lg"
              variant="primary"
              className="pointer-events-auto !border !border-white/30 !shadow-none"
              label={t('speech.play')}
              onClick={() => {
                void video.current?.play().catch(() => setPlayBlocked(true));
              }}
            >
              <PlayIcon className="h-5 w-5" />
            </BrutalIconButton>
          </div>
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
      {menu && video.current && (
        <VideoContextMenu
          anchor={menu}
          video={video.current}
          onClose={() => setMenu(null)}
          onError={() => setPlayBlocked(true)}
        />
      )}
      {playBlocked && (
        <p role="status" className="px-3 pb-2 text-xs text-neutral-500">
          {t('speech.playbackBlocked')}
        </p>
      )}
    </figure>
  );
}
