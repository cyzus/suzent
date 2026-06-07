import React from 'react';

import { getInitialLocale, tForLocale } from '../i18n';

interface BackendLoadingScreenProps {
  error?: string | null;
  onRetry?: () => void;
}

// Map each setup step message to a progress percentage.
// Steps that aren't listed fall back to the previous progress value.
const STEP_PROGRESS: Record<string, number> = {
  'Setting up Python environment...': 5,
  'Creating Python virtual environment...': 20,
  'Installing packages...': 45,
  'Installing Playwright Chromium browser (this may take a few minutes)...': 70,
  'Finalizing setup...': 88,
  'Starting backend server...': 95,
  'Starting backend...': 95,
};

export function BackendLoadingScreen({ error, onRetry }: BackendLoadingScreenProps): React.ReactElement {
  const locale = getInitialLocale();
  const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);
  const appWindow = window.__TAURI__?.window.getCurrentWindow();
  const [setupStep, setSetupStep] = React.useState<string | null>(null);
  const [progress, setProgress] = React.useState(0);
  const [ambientProgress, setAmbientProgress] = React.useState(18);
  const [isMaximized, setIsMaximized] = React.useState(false);

  async function handleDrag(event: React.MouseEvent<HTMLDivElement>): Promise<void> {
    const target = event.target as HTMLElement;
    if (target.closest('button')) return;
    await appWindow?.startDragging();
  }

  async function handleMaximize(): Promise<void> {
    await appWindow?.toggleMaximize();
    setIsMaximized(prev => !prev);
  }

  React.useEffect(() => {
    if (error) return;
    const interval = setInterval(() => {
      const step = (window as any).__SUZENT_SETUP_STEP__;
      if (step && step !== setupStep) {
        setSetupStep(step);
        const pct = STEP_PROGRESS[step];
        if (pct !== undefined) setProgress(pct);
      }
    }, 150);
    return () => clearInterval(interval);
  }, [error, setupStep]);

  React.useEffect(() => {
    if (error || progress > 0) return;
    const interval = window.setInterval(() => {
      setAmbientProgress(prev => {
        if (prev >= 86) return 18;
        return prev + Math.max(2, Math.round((86 - prev) * 0.08));
      });
    }, 420);
    return () => window.clearInterval(interval);
  }, [error, progress]);

  const displayProgress = progress > 0 ? progress : ambientProgress;

  return (
    <div className="flex h-screen w-screen flex-col bg-neutral-100 font-sans text-center overflow-hidden">
      <style>{`
        @keyframes suzentPanelSignal {
          0% { transform: translateX(-110%); opacity: 0; }
          20% { opacity: .18; }
          52% { opacity: .08; }
          100% { transform: translateX(110%); opacity: 0; }
        }
        @keyframes suzentProgressPulse {
          0%, 100% { filter: brightness(1); }
          50% { filter: brightness(1.35); }
        }
        @keyframes suzentTick {
          0%, 100% { transform: scaleY(.25); opacity: .35; }
          50% { transform: scaleY(1); opacity: 1; }
        }
        @keyframes suzentCube3dTurn {
          0% { transform: rotateX(-22deg) rotateY(32deg) rotateZ(0deg); }
          35% { transform: rotateX(18deg) rotateY(132deg) rotateZ(8deg); }
          70% { transform: rotateX(-34deg) rotateY(246deg) rotateZ(-8deg); }
          100% { transform: rotateX(-22deg) rotateY(392deg) rotateZ(0deg); }
        }
        @keyframes suzentCubeBreath {
          0%, 100% { transform: translateZ(0) scale(1); filter: brightness(1); }
          50% { transform: translateZ(12px) scale(1.04); filter: brightness(1.18); }
        }
        @keyframes suzentOccultRing {
          0% { transform: rotate(var(--start-rotation)) scale(1); opacity: .38; }
          50% { transform: rotate(calc(var(--start-rotation) + 178deg)) scale(1.045); opacity: .78; }
          100% { transform: rotate(calc(var(--start-rotation) + 360deg)) scale(1); opacity: .38; }
        }
        @keyframes suzentRuneBlink {
          0%, 100% { opacity: .22; transform: rotate(var(--rune-rotation)) translateY(-80px) scale(.86); }
          45% { opacity: 1; transform: rotate(var(--rune-rotation)) translateY(-87px) scale(1); }
          70% { opacity: .44; transform: rotate(var(--rune-rotation)) translateY(-76px) scale(.92); }
        }
        @keyframes suzentCoreSlice {
          0%, 100% { transform: translateY(0) scaleX(.72); opacity: .22; }
          50% { transform: translateY(var(--slice-y)) scaleX(1); opacity: .9; }
        }
        .suzent-cube-scene {
          perspective: 680px;
          transform-style: preserve-3d;
        }
        .suzent-cube {
          transform-style: preserve-3d;
          animation: suzentCube3dTurn 5.8s cubic-bezier(.4, 0, .2, 1) infinite;
        }
        .suzent-cube-face {
          position: absolute;
          inset: 0;
          background: #000;
          border: 1px solid rgba(255,255,255,.16);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,.06);
        }
      `}</style>
      <div
        className="h-10 shrink-0 bg-white border-b border-neutral-200 flex items-center justify-between px-4 select-none"
        onMouseDown={handleDrag}
        data-tauri-drag-region
      >
        <div className="flex items-center gap-2 pointer-events-none">
          <div className="h-2.5 w-2.5 bg-brutal-black" />
          <span className="font-brutal text-xs uppercase text-brutal-black">SUZENT</span>
        </div>
        <div className="flex h-full items-center text-brutal-black">
          <button
            type="button"
            onMouseDown={(event) => event.stopPropagation()}
            onClick={() => appWindow?.minimize()}
            className="h-full w-10 flex items-center justify-center hover:bg-neutral-100"
            title={t('titlebar.minimize')}
          >
            <span className="h-0.5 w-3 bg-current" />
          </button>
          <button
            type="button"
            onMouseDown={(event) => event.stopPropagation()}
            onClick={handleMaximize}
            className="h-full w-10 flex items-center justify-center hover:bg-neutral-100"
            title={isMaximized ? t('titlebar.restore') : t('titlebar.maximize')}
          >
            <span className="h-3 w-3 border-2 border-current" />
          </button>
          <button
            type="button"
            onMouseDown={(event) => event.stopPropagation()}
            onClick={() => appWindow?.close()}
            className="h-full w-10 flex items-center justify-center hover:bg-brutal-red hover:text-white"
            title={t('titlebar.close')}
          >
            <span className="text-lg leading-none">×</span>
          </button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="relative bg-white p-8 border border-neutral-300 shadow-[6px_6px_0px_0px_rgba(0,0,0,0.92)] max-w-md w-full flex flex-col items-center overflow-hidden">
          {!error && (
            <div
              className="pointer-events-none absolute inset-y-0 left-0 w-1/3 bg-black"
              style={{
                animation: 'suzentPanelSignal 2.8s ease-in-out infinite',
                clipPath: 'polygon(22% 0, 100% 0, 78% 100%, 0 100%)',
              }}
            />
          )}
          <div className="relative mb-6 flex h-44 w-44 items-center justify-center" aria-hidden="true">
            {!error && (
              <>
                {[0, 1, 2].map(idx => (
                  <div
                    key={`ring-${idx}`}
                    className="absolute rounded-full border border-brutal-black"
                    style={{
                      width: `${132 + idx * 22}px`,
                      height: `${132 + idx * 22}px`,
                      '--start-rotation': `${idx * 31}deg`,
                      opacity: 0.18 + idx * 0.08,
                      transform: `rotate(${idx * 31}deg)`,
                      animation: `suzentOccultRing ${5.4 + idx * 1.2}s linear infinite`,
                    } as React.CSSProperties}
                  >
                    <span className="absolute left-1/2 top-[-3px] h-1.5 w-8 -translate-x-1/2 bg-white" />
                    <span className="absolute bottom-[-3px] left-1/2 h-1.5 w-8 -translate-x-1/2 bg-white" />
                    <span className="absolute left-[-3px] top-1/2 h-8 w-1.5 -translate-y-1/2 bg-white" />
                    <span className="absolute right-[-3px] top-1/2 h-8 w-1.5 -translate-y-1/2 bg-white" />
                  </div>
                ))}
                {Array.from({ length: 12 }).map((_, idx) => (
                  <span
                    key={`rune-${idx}`}
                    className="absolute left-1/2 top-1/2 h-3 w-1.5 origin-[50%_0] bg-brutal-black"
                    style={{
                      '--rune-rotation': `${idx * 30}deg`,
                      animation: 'suzentRuneBlink 2.6s steps(2, end) infinite',
                      animationDelay: `${idx * 0.09}s`,
                    } as React.CSSProperties}
                  />
                ))}
              </>
            )}
            <div className={`suzent-cube-scene relative h-28 w-28 ${error ? 'opacity-35' : ''}`}>
            <div
              className="suzent-cube absolute inset-0"
              style={!error ? { animationName: 'suzentCube3dTurn' } : { transform: 'rotateX(-18deg) rotateY(36deg)' }}
            >
              <div className="suzent-cube-face" style={{ transform: 'translateZ(56px)' }} />
              <div className="suzent-cube-face" style={{ transform: 'rotateY(180deg) translateZ(56px)', opacity: .74 }} />
              <div className="suzent-cube-face" style={{ transform: 'rotateY(90deg) translateZ(56px)', opacity: .86 }} />
              <div className="suzent-cube-face" style={{ transform: 'rotateY(-90deg) translateZ(56px)', opacity: .58 }} />
              <div className="suzent-cube-face" style={{ transform: 'rotateX(90deg) translateZ(56px)', opacity: .92 }} />
              <div className="suzent-cube-face" style={{ transform: 'rotateX(-90deg) translateZ(56px)', opacity: .5 }} />
              <div
                className="absolute left-7 top-7 h-14 w-14 border border-white/80"
                style={{
                  transform: 'translateZ(58px)',
                  animation: !error ? 'suzentCubeBreath 2.2s ease-in-out infinite' : undefined,
                }}
              />
              {[0, 1, 2].map(idx => (
                <span
                  key={`slice-${idx}`}
                  className="absolute left-3 top-1/2 h-px w-20 bg-white/70"
                  style={{
                    '--slice-y': `${(idx - 1) * 18}px`,
                    transform: `translateZ(${60 + idx}px) translateY(${(idx - 1) * 10}px)`,
                    animation: !error ? 'suzentCoreSlice 1.8s ease-in-out infinite' : undefined,
                    animationDelay: `${idx * 0.18}s`,
                  } as React.CSSProperties}
                />
              ))}
            </div>
          </div>
          {!error && (
            <>
              {Array.from({ length: 6 }).map((_, idx) => (
                <span
                  key={`orbit-${idx}`}
                  className="absolute left-1/2 top-1/2 h-2.5 w-2.5 bg-brutal-black"
                  style={{
                    transform: `rotate(${idx * 60}deg) translateX(92px) rotate(45deg)`,
                    opacity: idx % 2 === 0 ? .85 : .36,
                  }}
                />
              ))}
            </>
          )}
        </div>
        <h1 className="relative text-4xl font-brutal font-black uppercase mb-4 text-brutal-black">
          {error ? t('app.backendErrorTitle') : t('app.initializing')}
        </h1>
        <div className="relative mb-6 min-h-[2rem]">
          <p className="font-bold text-lg leading-tight">
            {error || setupStep || t('app.connectingToCore')}
          </p>
          {!error && (
            <div className="mt-3 flex items-end justify-center gap-1" aria-hidden="true">
              {Array.from({ length: 17 }).map((_, idx) => (
                <span
                  key={idx}
                  className="block w-1 bg-brutal-black"
                  style={{
                    height: `${8 + (idx % 5) * 4}px`,
                    animation: `suzentTick ${0.78 + (idx % 4) * 0.08}s ease-in-out infinite`,
                    animationDelay: `${idx * 0.06}s`,
                  }}
                />
              ))}
            </div>
          )}
        </div>
        {error && onRetry ? (
          <button
            onClick={onRetry}
            className="px-6 py-3 bg-brutal-black text-white font-bold uppercase border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all"
          >
            {t('common.retry')}
          </button>
        ) : (
          <div className="relative w-full">
            <div className="w-full h-4 bg-neutral-200 border-2 border-brutal-black overflow-hidden relative">
              <div
                className="absolute top-0 left-0 h-full bg-brutal-black transition-all duration-500 ease-out"
                style={{
                  width: `${displayProgress}%`,
                  animation: 'suzentProgressPulse 1.1s ease-in-out infinite',
                }}
              />
              <div
                className="absolute inset-y-0 w-12 bg-white/25"
                style={{
                  left: `${Math.max(0, displayProgress - 8)}%`,
                  transform: 'skewX(-18deg)',
                  transition: 'left 500ms ease-out',
                }}
              />
            </div>
            <p className="text-right text-xs font-mono mt-1 text-neutral-500">
              {displayProgress}%
            </p>
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
