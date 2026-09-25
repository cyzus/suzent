import React, { useEffect } from 'react';
import { useI18n } from '../i18n';
import { FullscreenOverlay } from './FullscreenOverlay';

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

  const index = src ? images.indexOf(src) : -1;
  const canNavigate = index >= 0 && images.length > 1 && Boolean(onNavigate);
  const previous = () => onNavigate?.(images[(index - 1 + images.length) % images.length]);
  const next = () => onNavigate?.(images[(index + 1) % images.length]);

  useEffect(() => {
    if (!src || !canNavigate) return;
    const handleKey = (event: KeyboardEvent) => {
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
    <FullscreenOverlay
      open={Boolean(src)}
      onClose={onClose}
      zIndexClassName="z-50"
      backdropClassName="bg-brutal-black/90 p-4 md:p-8 animate-in fade-in duration-200"
      containerClassName="relative max-w-full max-h-full flex flex-col items-center bg-transparent border-0 shadow-none"
    >
      <img
        src={src}
        alt={t('imageViewer.fullScreenAlt')}
        className="max-w-full max-h-[75vh] object-contain border-4 border-brutal-black shadow-brutal-xl bg-white"
      />
      {canNavigate && (
        <div className="mt-3 flex items-center gap-4 text-white">
          <button
            type="button"
            onClick={previous}
            aria-label={t('imageViewer.previous')}
            className="px-4 py-2 border border-white rounded-sm"
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
            className="px-4 py-2 border border-white rounded-sm"
          >
            →
          </button>
        </div>
      )}
      <button
        onClick={onClose}
        className="mt-4 px-6 py-2 bg-brutal-red text-white border-2 border-brutal-black font-bold text-sm uppercase shadow-[2px_2px_0_0_#000] brutal-btn"
      >
        {t('imageViewer.close')}
      </button>
    </FullscreenOverlay>
  );
};
