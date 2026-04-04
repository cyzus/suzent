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
        <div className={`absolute inset-0 bg-brutal-red z-30 animate-brutal-pop`}>
            <div className="absolute pointer-events-none inset-0 border-[3px] border-brutal-black" />
            <div className={`relative h-full flex ${isVertical ? 'flex-col items-center justify-center gap-2 p-2' : 'items-center justify-between px-3'} z-10`}>
                <span className={`${isVertical ? 'text-sm' : 'text-xs'} font-extrabold text-white text-center animate-brutal-glitch`}>
                    {effectiveTitle}
                </span>
                <div className={`flex ${isVertical ? 'gap-2' : 'gap-1.5'}`}>
                    <button
                        onClick={onConfirm}
                        disabled={isDeleting}
                        className="px-2.5 py-1 bg-brutal-black text-white text-[10px] font-extrabold disabled:opacity-50 hover:bg-neutral-800 transition-colors border border-brutal-black"
                    >
                        {isDeleting ? '...' : effectiveConfirmText}
                    </button>
                    <button
                        onClick={onCancel}
                        className="px-2.5 py-1 bg-white border border-brutal-black text-brutal-black text-[10px] font-extrabold hover:bg-neutral-100 transition-colors"
                    >
                        {effectiveCancelText}
                    </button>
                </div>
            </div>
        </div>
    );
};
