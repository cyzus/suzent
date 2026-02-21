import React from 'react';
import { useI18n } from '../i18n';

interface BrutalDeleteOverlayProps {
    onConfirm: (e: React.MouseEvent) => void;
    onCancel: (e: React.MouseEvent) => void;
    isDeleting?: boolean;
    title?: string;
    confirmText?: string;
    cancelText?: string;
    layout?: 'vertical' | 'horizontal';
}

export const BrutalDeleteOverlay: React.FC<BrutalDeleteOverlayProps> = ({
    onConfirm,
    onCancel,
    isDeleting = false,
    title,
    confirmText,
    cancelText,
    layout = 'vertical',
}) => {
    const { t } = useI18n();
    const effectiveTitle = title ?? t('deleteOverlay.title');
    const effectiveConfirmText = confirmText ?? t('deleteOverlay.confirm');
    const effectiveCancelText = cancelText ?? t('deleteOverlay.cancel');
    const isVertical = layout === 'vertical';

    return (
        <div className={`absolute inset-0 bg-brutal-red z-10 flex ${isVertical ? 'flex-col items-center justify-center gap-2 p-2' : 'items-center justify-between px-4'} animate-brutal-pop`}>
            <span className={`${isVertical ? 'text-sm' : 'text-xs'} font-bold text-white uppercase animate-brutal-glitch text-center`}>
                {effectiveTitle}
            </span>
            <div className={`flex ${isVertical ? 'gap-2' : 'gap-2'}`}>
                <button
                    onClick={onConfirm}
                    disabled={isDeleting}
                    className="px-3 py-1.5 bg-brutal-black border-2 border-brutal-black text-white text-xs font-bold uppercase disabled:opacity-50 hover:bg-neutral-800"
                >
                    {isDeleting ? '...' : effectiveConfirmText}
                </button>
                <button
                    onClick={onCancel}
                    className="px-3 py-1.5 bg-brutal-white border-2 border-brutal-black text-brutal-black text-xs font-bold uppercase hover:bg-neutral-100"
                >
                    {effectiveCancelText}
                </button>
            </div>
        </div>
    );
};
