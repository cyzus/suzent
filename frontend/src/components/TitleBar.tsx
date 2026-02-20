import React from 'react';
import { useI18n } from '../i18n';

export const TitleBar: React.FC = () => {
    const { t } = useI18n();
    const [isTauri, setIsTauri] = React.useState(false);
    const [isMaximized, setIsMaximized] = React.useState(false);

    React.useEffect(() => {
        setIsTauri(!!window.__TAURI__);
    }, []);

    if (!isTauri) return null;

    const appWindow = window.__TAURI__?.window.getCurrentWindow();

    const handleMaximize = async () => {
        await appWindow?.toggleMaximize();
        // Toggle local state for icon swap
        setIsMaximized(!isMaximized);
    };

    return (
        <div
            className="h-8 bg-brutal-white flex items-center justify-between select-none fixed top-0 left-0 right-0 z-[9999] border-b-3 border-brutal-black"
        >
            {/* Drag Region & Title */}
            <div className="flex-1 h-full flex items-center pl-4" data-tauri-drag-region>
                <span className="font-brutal text-sm uppercase tracking-tight text-brutal-black pointer-events-none mt-0.5">
                    {t('app.title')}
                </span>
            </div>

            {/* Window Controls */}
            <div className="flex h-full text-brutal-black">
                {/* Minimize */}
                <button
                    onClick={() => appWindow?.minimize()}
                    className="h-full w-11 flex items-center justify-center hover:bg-brutal-black hover:text-brutal-white transition-colors"
                    title={t('titlebar.minimize')}
                >
                    <svg width="10" height="2" viewBox="0 0 10 2" fill="currentColor">
                        <rect width="10" height="2" />
                    </svg>
                </button>

                {/* Maximize / Restore */}
                <button
                    onClick={handleMaximize}
                    className="h-full w-11 flex items-center justify-center hover:bg-brutal-black hover:text-brutal-white transition-colors"
                    title={isMaximized ? t('titlebar.restore') : t('titlebar.maximize')}
                >
                    {isMaximized ? (
                        // Restore icon: two overlapping squares
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="2" y="0" width="8" height="8" rx="0" />
                            <rect x="0" y="2" width="8" height="8" rx="0" fill="currentColor" className="text-brutal-white" />
                            <rect x="0" y="2" width="8" height="8" rx="0" />
                        </svg>
                    ) : (
                        // Maximize icon: single square
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="0" y="0" width="10" height="10" rx="0" />
                        </svg>
                    )}
                </button>

                {/* Close */}
                <button
                    onClick={() => appWindow?.close()}
                    className="h-full w-11 flex items-center justify-center hover:bg-brutal-red hover:text-white transition-colors"
                    title={t('titlebar.close')}
                >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="0" y1="0" x2="10" y2="10" />
                        <line x1="10" y1="0" x2="0" y2="10" />
                    </svg>
                </button>
            </div>
        </div>
    );
};
