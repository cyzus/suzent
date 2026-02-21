import React, { useEffect } from 'react';
import { useI18n } from '../i18n';

interface ImageViewerProps {
    src: string | null;
    onClose: () => void;
}

export const ImageViewer: React.FC<ImageViewerProps> = ({ src, onClose }) => {
    const { t } = useI18n();

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };

        if (src) {
            window.addEventListener('keydown', handleKeyDown);
            document.body.style.overflow = 'hidden';
        }

        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            document.body.style.overflow = '';
        };
    }, [src, onClose]);

    if (!src) return null;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-brutal-black/90 p-4 md:p-8 animate-in fade-in duration-200"
            onClick={onClose}
        >
            <div className="relative max-w-full max-h-full flex flex-col items-center">
                <img
                    src={src}
                    alt={t('imageViewer.fullScreenAlt')}
                    className="max-w-full max-h-[85vh] object-contain border-4 border-brutal-black shadow-brutal-xl bg-white"
                    onClick={(e) => e.stopPropagation()}
                />
                <button
                    onClick={onClose}
                    className="mt-4 px-6 py-2 bg-brutal-red text-white border-2 border-brutal-black font-bold text-sm uppercase shadow-[2px_2px_0_0_#000] brutal-btn"
                >
                    Close
                </button>
            </div>
        </div>
    );
};
