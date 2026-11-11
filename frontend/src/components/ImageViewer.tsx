import { ZoomableImage } from './ZoomableImage';
import { BrutalIconButton } from './BrutalButton';
import { ChevronLeftIcon, ChevronRightIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Dialog } from '@headlessui/react';
import React, { useEffect, useRef } from 'react';
import { useI18n } from '../i18n';
import { isImeComposing } from '../lib/ime';

const viewerButtonClass =
  '!h-9 !w-9 rounded-sm !border !border-white/20 !bg-zinc-900/70 !text-neutral-200 !shadow-none hover:!border-white/40 hover:!bg-zinc-800 hover:!text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900';

const navigationButtonClass =
  '!h-8 !w-8 rounded-sm !border-0 !bg-transparent !text-neutral-300 !shadow-none hover:!bg-white/10 hover:!text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-white/60';

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
    <Dialog open onClose={onClose} className="relative z-[1000]">
      <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" aria-hidden="true" />
      <div className="fixed inset-0">
        <Dialog.Panel className="relative h-full w-full overflow-hidden">
          <Dialog.Title className="sr-only">{t('imageViewer.fullScreenAlt')}</Dialog.Title>
          <BrutalIconButton
            variant="ghost"
            onClick={onClose}
            label={t('imageViewer.close')}
            className={`absolute right-4 top-4 z-10 ${viewerButtonClass}`}
          >
            <XMarkIcon className="h-5 w-5" strokeWidth={1.5} />
          </BrutalIconButton>
          <div className="h-full w-full">
            <ZoomableImage
              key={src}
              src={src}
              alt={t('imageViewer.fullScreenAlt')}
              imageRef={image}
            />
            {canNavigate && (
              <div className="absolute bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-md border border-white/10 bg-zinc-900/85 p-1 text-neutral-300 shadow-lg backdrop-blur-md">
                <BrutalIconButton
                  type="button"
                  variant="ghost"
                  className={navigationButtonClass}
                  onClick={previous}
                  label={t('imageViewer.previous')}
                >
                  <ChevronLeftIcon className="h-4 w-4" strokeWidth={1.5} />
                </BrutalIconButton>
                <span
                  aria-live="polite"
                  className="shrink-0 whitespace-nowrap text-center font-mono text-[11px] font-normal tracking-wide tabular-nums"
                  style={{ width: `${String(images.length).length * 2 + 5}ch` }}
                >
                  {index + 1} / {images.length}
                </span>
                <BrutalIconButton
                  type="button"
                  variant="ghost"
                  className={navigationButtonClass}
                  onClick={next}
                  label={t('imageViewer.next')}
                >
                  <ChevronRightIcon className="h-4 w-4" strokeWidth={1.5} />
                </BrutalIconButton>
              </div>
            )}
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
};
