import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

interface FullscreenOverlayProps {
  open: boolean;
  onClose?: () => void;
  children: React.ReactNode;
  closeOnEscape?: boolean;
  closeOnBackdrop?: boolean;
  lockBodyScroll?: boolean;
  backdropClassName?: string;
  containerClassName?: string;
  zIndexClassName?: string;
}

export const FullscreenOverlay: React.FC<FullscreenOverlayProps> = ({
  open,
  onClose,
  children,
  closeOnEscape = true,
  closeOnBackdrop = true,
  lockBodyScroll = true,
  backdropClassName = 'bg-brutal-black/80 backdrop-blur-sm p-4',
  containerClassName = 'w-full max-w-6xl h-[90vh] bg-white dark:bg-zinc-900 border-4 border-brutal-black shadow-brutal-xl flex flex-col',
  zIndexClassName = 'z-[120]',
}) => {
  useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;

    if (lockBodyScroll) {
      document.body.style.overflow = 'hidden';
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (closeOnEscape && e.key === 'Escape') {
        onClose?.();
      }
    };

    window.addEventListener('keydown', onKeyDown);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      if (lockBodyScroll) {
        document.body.style.overflow = previousOverflow;
      }
    };
  }, [open, closeOnEscape, lockBodyScroll, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className={`fixed inset-0 ${zIndexClassName} flex items-center justify-center ${backdropClassName}`}
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      <div className={containerClassName} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>,
    document.body
  );
};
