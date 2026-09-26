import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n';

export function VideoContextMenu({
  anchor,
  video,
  onClose,
  onError,
  onReveal,
}: {
  anchor: { x: number; y: number };
  video: HTMLVideoElement;
  onClose: () => void;
  onError: () => void;
  onReveal?: () => Promise<void>;
}): React.ReactElement {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: -9999, top: -9999 });
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu) return;
    setPosition({
      left: Math.max(8, Math.min(anchor.x, window.innerWidth - menu.offsetWidth - 8)),
      top: Math.max(8, Math.min(anchor.y, window.innerHeight - menu.offsetHeight - 8)),
    });
    menu.querySelector<HTMLButtonElement>('button')?.focus();
  }, [anchor]);
  useEffect(() => {
    const dismiss = (event: Event) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    const close = () => onClose();
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [onClose]);
  const items = [
    ...(onReveal ? [{ label: t('videoPlayer.reveal'), action: onReveal }] : []),
    {
      label: t(video.paused ? 'speech.play' : 'videoPlayer.pause'),
      action: async () => {
        if (video.paused) await video.play();
        else video.pause();
      },
    },
    {
      label: t(video.muted ? 'videoPlayer.unmute' : 'videoPlayer.mute'),
      action: () => {
        video.muted = !video.muted;
      },
    },
    {
      label: t(video.loop ? 'videoPlayer.stopLoop' : 'videoPlayer.loop'),
      action: () => {
        video.loop = !video.loop;
      },
    },
    ...(document.fullscreenEnabled
      ? [{ label: t('videoPlayer.fullscreen'), action: () => video.requestFullscreen() }]
      : []),
  ];
  return createPortal(
    <div
      ref={ref}
      role="menu"
      aria-label={t('videoPlayer.menu')}
      className="fixed z-[9999] min-w-40 border border-neutral-200 bg-white py-1 shadow-sm dark:border-zinc-700 dark:bg-zinc-800"
      style={position}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onKeyDown={(event) => {
        event.stopPropagation();
        const buttons = Array.from(
          ref.current?.querySelectorAll<HTMLButtonElement>('button') ?? []
        );
        const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
        if (event.key === 'Escape' || event.key === 'Tab') {
          onClose();
          video.focus();
        }
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const next =
            event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? buttons.length - 1
                : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
          buttons[next]?.focus();
        }
      }}
    >
      {items.map(({ label, action }) => (
        <button
          key={label}
          type="button"
          role="menuitem"
          className="block w-full px-3 py-2 text-left text-xs font-mono text-brutal-black hover:bg-neutral-100 focus:bg-neutral-100 focus:outline-none dark:text-white dark:hover:bg-zinc-700 dark:focus:bg-zinc-700"
          onClick={() => {
            onClose();
            video.focus();
            void Promise.resolve().then(action).catch(onError);
          }}
        >
          {label}
        </button>
      ))}
    </div>,
    document.fullscreenElement ?? document.body
  );
}
