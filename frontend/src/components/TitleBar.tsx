import React from 'react';
import { useI18n } from '../i18n';
import { desktopWindow, isDesktop } from '../lib/desktop';
import { detectDesktopPlatform, type DesktopPlatform } from '../lib/titleBarPlatform';

export const TitleBar: React.FC<{ startup?: boolean }> = ({ startup = false }) => {
  const [desktop, setDesktop] = React.useState(false);
  const [isMaximized, setIsMaximized] = React.useState(false);
  const [platform, setPlatform] = React.useState<DesktopPlatform>('unknown');
  const { t } = useI18n();

  React.useEffect(() => {
    setDesktop(isDesktop());
    setPlatform(detectDesktopPlatform(navigator.userAgent, navigator.platform));
  }, []);

  if (!desktop || (platform === 'windows' && !startup) || platform === 'macos') return null;

  const windowsStartup = startup && platform === 'windows';
  const controlWidth = 'w-11';

  const handleMaximize = async () => {
    await desktopWindow.toggleMaximize();
    // Toggle local state for icon swap
    setIsMaximized(!isMaximized);
  };

  const closeButtonClass = `h-full ${controlWidth} flex items-center justify-center hover:bg-brutal-red hover:text-white transition-colors`;

  const minimizeButtonClass = `h-full ${controlWidth} flex items-center justify-center hover:bg-brutal-black dark:hover:bg-zinc-600 hover:text-brutal-white transition-colors`;

  const maximizeButtonClass = `h-full ${controlWidth} flex items-center justify-center hover:bg-brutal-black dark:hover:bg-zinc-600 hover:text-brutal-white transition-colors`;

  // The startup screen has its own wordmark, so on Windows it only keeps
  // the window controls floating over a drag strip.
  return (
    <div
      className={`${windowsStartup ? 'h-10 bg-transparent' : 'h-8 bg-brutal-white dark:bg-zinc-800 border-b-3 border-brutal-black'} flex items-center justify-between select-none fixed top-0 left-0 right-0 z-[9999]`}
    >
      <div
        className={`flex-1 h-full flex items-center ${windowsStartup ? '' : 'pl-4'}`}
        data-tauri-drag-region
      >
        {!windowsStartup && (
          <span className="font-brutal text-sm mt-0.5 uppercase tracking-tight text-brutal-black dark:text-white pointer-events-none leading-none">
            {t('app.title').toUpperCase()}
          </span>
        )}
      </div>

      {/* Window controls */}
      <div
        className={`flex h-full text-brutal-black dark:text-white ${windowsStartup ? 'absolute right-0 top-0 bottom-0 text-neutral-500' : ''}`}
        data-no-drag
      >
        {/* Minimize */}
        <button
          onClick={() => desktopWindow.minimize()}
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
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="2" y="0" width="8" height="8" rx="0" />
              <rect
                x="0"
                y="2"
                width="8"
                height="8"
                rx="0"
                fill="currentColor"
                className="text-brutal-white"
              />
              <rect x="0" y="2" width="8" height="8" rx="0" />
            </svg>
          ) : (
            // Maximize icon: single square
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="0" y="0" width="10" height="10" rx="0" />
            </svg>
          )}
        </button>

        {/* Close */}
        <button
          onClick={() => desktopWindow.close()}
          className={closeButtonClass}
          title={t('titlebar.close')}
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <line x1="0" y1="0" x2="10" y2="10" />
            <line x1="10" y1="0" x2="0" y2="10" />
          </svg>
        </button>
      </div>
    </div>
  );
};
