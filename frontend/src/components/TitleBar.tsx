import React from 'react';
import { useI18n } from '../i18n';
import { detectDesktopPlatform, type DesktopPlatform } from '../lib/titleBarPlatform';

export const TitleBar: React.FC = () => {
    const [isTauri, setIsTauri] = React.useState(false);
    const [isMaximized, setIsMaximized] = React.useState(false);
    const [platform, setPlatform] = React.useState<DesktopPlatform>('unknown');
    const { t } = useI18n();

    React.useEffect(() => {
        setIsTauri(!!window.__TAURI__);
        setPlatform(detectDesktopPlatform(navigator.userAgent, navigator.platform));
    }, []);

    if (!isTauri || platform === 'windows') return null;

    const appWindow = window.__TAURI__?.window.getCurrentWindow();

    const handleMaximize = async () => {
        await appWindow?.toggleMaximize();
        // Toggle local state for icon swap
        setIsMaximized(!isMaximized);
    };

    const isMacOS = platform === 'macos';
    const closeButtonClass = isMacOS
        ? 'h-3 w-3 rounded-full bg-[#ff5f57] border border-[#e0443e]'
        : 'h-full w-11 flex items-center justify-center hover:bg-brutal-red hover:text-white transition-colors';

    const minimizeButtonClass = isMacOS
        ? 'h-3 w-3 rounded-full bg-[#febc2e] border border-[#dfa123]'
        : 'h-full w-11 flex items-center justify-center hover:bg-brutal-black dark:hover:bg-zinc-600 hover:text-brutal-white transition-colors';

    const maximizeButtonClass = isMacOS
        ? 'h-3 w-3 rounded-full bg-[#28c840] border border-[#1ea833]'
        : 'h-full w-11 flex items-center justify-center hover:bg-brutal-black dark:hover:bg-zinc-600 hover:text-brutal-white transition-colors';

    return (
        <div
            className="h-8 bg-brutal-white dark:bg-zinc-800 flex items-center justify-between select-none fixed top-0 left-0 right-0 z-[9999] border-b-3 border-brutal-black"
        >
            {/* macOS-style traffic lights */}
            {isMacOS ? (
                <div className="h-full flex items-center gap-2 pl-3 pr-3">
                    <button
                        onClick={() => appWindow?.close()}
                        className={`${closeButtonClass} transition-opacity hover:opacity-90`}
                        title={t('titlebar.close')}
                    />
                    <button
                        onClick={() => appWindow?.minimize()}
                        className={`${minimizeButtonClass} transition-opacity hover:opacity-90`}
                        title={t('titlebar.minimize')}
                    />
                    <button
                        onClick={handleMaximize}
                        className={`${maximizeButtonClass} transition-opacity hover:opacity-90`}
                        title={isMaximized ? t('titlebar.restore') : t('titlebar.maximize')}
                    />
                </div>
            ) : null}

            {/* Drag Region & Title */}
            <div className={`flex-1 h-full flex items-center ${isMacOS ? 'justify-center pr-20' : 'pl-4'}`} data-tauri-drag-region>
                <span className="font-brutal text-sm uppercase tracking-tight text-brutal-black dark:text-white pointer-events-none mt-0.5 leading-none">
                    {t('app.title').toUpperCase()}
                </span>
            </div>

            {/* Windows/Linux controls */}
            {!isMacOS ? (
            <div className="flex h-full text-brutal-black dark:text-white">
                {/* Minimize */}
                <button
                    onClick={() => appWindow?.minimize()}
                    className={minimizeButtonClass}
                    title={t('titlebar.minimize')}
                >
                    <svg width="10" height="2" viewBox="0 0 10 2" fill="currentColor">
                        <rect width="10" height="2" />
                    </svg>
                </button>

                {/* Maximize / Restore */}
                <button
                    onClick={handleMaximize}
                    className={maximizeButtonClass}
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
                    className={closeButtonClass}
                    title={t('titlebar.close')}
                >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="0" y1="0" x2="10" y2="10" />
                        <line x1="10" y1="0" x2="0" y2="10" />
                    </svg>
                </button>
            </div>
            ) : null}
        </div>
    );
};
