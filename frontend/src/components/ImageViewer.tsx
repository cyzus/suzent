import React, { useEffect, useRef } from 'react';
import { useI18n } from '../i18n';
import { isImeComposing } from '../lib/ime';
import { WorkspacePanel } from './WorkspacePanel';

interface ImageViewerProps {
  src: string | null;
  onClose: () => void;
  images?: string[];
  onNavigate?: (src: string) => void;
}

export const ImageViewer: React.FC<ImageViewerProps> = ({
  src,
  onClose,
  images = [],
  onNavigate,
}) => {
  const { t } = useI18n();
  const image = useRef<HTMLImageElement>(null);

  const index = src ? images.indexOf(src) : -1;
  const canNavigate = index >= 0 && images.length > 1 && Boolean(onNavigate);
  const previous = () => onNavigate?.(images[(index - 1 + images.length) % images.length]);
  const next = () => onNavigate?.(images[(index + 1) % images.length]);

  useEffect(() => {
    if (!src || !canNavigate) return;
    const handleKey = (event: KeyboardEvent) => {
      if (isImeComposing(event)) return;
      if (!image.current?.getClientRects().length) return;
      if ((event.target as HTMLElement)?.closest('input, textarea, select, [contenteditable]'))
        return;
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const offset = event.key === 'ArrowLeft' ? -1 : 1;
      onNavigate?.(images[(index + offset + images.length) % images.length]);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [src, canNavigate, images, index, onNavigate]);

  if (!src) return null;

  return (
    <WorkspacePanel
      open={Boolean(src)}
      className="flex-col items-center justify-center gap-3 p-4 md:p-8"
      onClose={onClose}
    >
      <img
        ref={image}
        src={src}
        alt={t('imageViewer.fullScreenAlt')}
        className="min-h-0 flex-1 max-w-full object-contain border-4 border-brutal-black shadow-brutal-xl bg-white"
      />
      {canNavigate && (
        <div className="shrink-0 flex items-center gap-4">
          <button
            type="button"
            onClick={previous}
            aria-label={t('imageViewer.previous')}
            className="px-4 py-2 border border-current rounded-sm"
          >
            ←
          </button>
          <span aria-live="polite" className="text-sm tabular-nums">
            {index + 1} / {images.length}
          </span>
          <button
            type="button"
            onClick={next}
            aria-label={t('imageViewer.next')}
            className="px-4 py-2 border border-current rounded-sm"
          >
            →
          </button>
        </div>
      )}
      <button
        onClick={onClose}
        className="shrink-0 px-6 py-2 bg-brutal-red text-white border-2 border-brutal-black font-bold text-sm uppercase shadow-[2px_2px_0_0_#000] brutal-btn"
      >
        {t('imageViewer.close')}
      </button>
    </WorkspacePanel>
  );
};
