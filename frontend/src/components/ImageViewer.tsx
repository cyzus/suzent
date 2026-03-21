import React from 'react';
import { useI18n } from '../i18n';
import { FullscreenOverlay } from './FullscreenOverlay';

interface ImageViewerProps {
    src: string | null;
    onClose: () => void;
}

export const ImageViewer: React.FC<ImageViewerProps> = ({ src, onClose }) => {
    const { t } = useI18n();

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
                className="max-w-full max-h-[85vh] object-contain border-4 border-brutal-black shadow-brutal-xl bg-white"
            />
            <button
                onClick={onClose}
                className="mt-4 px-6 py-2 bg-brutal-red text-white border-2 border-brutal-black font-bold text-sm uppercase shadow-[2px_2px_0_0_#000] brutal-btn"
            >
                Close
            </button>
        </FullscreenOverlay>
    );
};
