import { BrutalIconButton } from './BrutalButton';
import { ExpandedSurfaceCard } from './ExpandedSurfaceCard';
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
    <WorkspacePanel open={Boolean(src)} className="flex-col" onClose={onClose}>
      <ExpandedSurfaceCard title={t('imageViewer.fullScreenAlt')} onShrink={onClose}>
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-4 md:p-8">
          <img
            ref={image}
            src={src}
            alt={t('imageViewer.fullScreenAlt')}
            className="min-h-0 flex-1 max-w-full object-contain"
          />
          {canNavigate && (
            <div className="shrink-0 flex items-center gap-4">
              <BrutalIconButton type="button" onClick={previous} label={t('imageViewer.previous')}>
                ←
              </BrutalIconButton>
              <span aria-live="polite" className="text-sm tabular-nums">
                {index + 1} / {images.length}
              </span>
              <BrutalIconButton type="button" onClick={next} label={t('imageViewer.next')}>
                →
              </BrutalIconButton>
            </div>
          )}
        </div>
      </ExpandedSurfaceCard>
    </WorkspacePanel>
  );
};
