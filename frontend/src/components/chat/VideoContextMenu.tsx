import React from 'react';
import { ContextMenu } from '../ContextMenu';
import { itemBase, itemDefault } from '../contextMenuStyles';
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
  return (
    <ContextMenu
      anchor={anchor}
      onClose={onClose}
      returnFocus={video}
      label={t('videoPlayer.menu')}
    >
      {items.map(({ label, action }) => (
        <button
          key={label}
          type="button"
          role="menuitem"
          className={`${itemBase} ${itemDefault}`}
          onClick={() => {
            onClose();
            video.focus();
            void Promise.resolve().then(action).catch(onError);
          }}
        >
          {label}
        </button>
      ))}
    </ContextMenu>
  );
}
