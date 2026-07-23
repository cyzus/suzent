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

  const hasMeasuredProgress = progress > 0;

  return (
    <div className="flex h-screen w-screen flex-col bg-neutral-100 font-sans text-center overflow-hidden">
      <style>{`
        @keyframes suzentCoreTurn {
          0% { transform: rotateX(-20deg) rotateY(32deg); }
          50% { transform: rotateX(-12deg) rotateY(212deg); }
          100% { transform: rotateX(-20deg) rotateY(392deg); }
        }
        @keyframes suzentOrbitTurn {
          to { transform: rotate(360deg); }
        }
        @keyframes suzentOrbitTurnReverse {
          to { transform: rotate(-360deg); }
        }
        @keyframes suzentCoreGlow {
          0%, 100% { opacity: .08; transform: scale(.82); }
          50% { opacity: .16; transform: scale(1); }
        }
        @keyframes suzentIndeterminateProgress {
          0% { left: -28%; width: 22%; }
          45% { left: 38%; width: 34%; }
          100% { left: 106%; width: 22%; }
        }
        .suzent-cube-scene {
          perspective: 520px;
          transform-style: preserve-3d;
        }
        .suzent-cube {
          transform-style: preserve-3d;
          animation: suzentCoreTurn 7s cubic-bezier(.45, 0, .25, 1) infinite;
        }
        .suzent-cube-face {
          position: absolute;
          inset: 0;
          background: rgba(12, 12, 12, .96);
          border: 1px solid rgba(255, 255, 255, .22);
          box-shadow: inset 0 0 24px rgba(255, 255, 255, .035);
        }
        @media (prefers-reduced-motion: reduce) {
          .suzent-cube,
          .suzent-orbit,
          .suzent-orbit-reverse,
          .suzent-core-glow,
          .suzent-indeterminate-progress {
            animation: none !important;
          }
          .suzent-indeterminate-progress {
            left: 0;
            width: 32%;
          }
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
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-8">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage: 'linear-gradient(to right, #000 1px, transparent 1px), linear-gradient(to bottom, #000 1px, transparent 1px)',
            backgroundSize: '44px 44px',
            maskImage: 'radial-gradient(circle at center, black, transparent 68%)',
          }}
        />
        <main className="relative flex w-full max-w-sm flex-col items-center">
          <div className="relative mb-10 flex h-40 w-40 items-center justify-center" aria-hidden="true">
            <div
              className="suzent-core-glow absolute h-32 w-32 rounded-full bg-black blur-3xl"
              style={{ animation: !error ? 'suzentCoreGlow 3.4s ease-in-out infinite' : undefined }}
            />
            <div
              className="suzent-orbit absolute h-40 w-40 rounded-full border border-neutral-300"
              style={{ animation: !error ? 'suzentOrbitTurn 12s linear infinite' : undefined }}
            >
              <span className="absolute -top-0.5 left-1/2 h-1 w-8 -translate-x-1/2 bg-neutral-100" />
              <span className="absolute -right-1 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-black" />
            </div>
            <div
              className="suzent-orbit-reverse absolute h-[7.75rem] w-[7.75rem] rounded-full border border-dashed border-neutral-400/70"
              style={{ animation: !error ? 'suzentOrbitTurnReverse 18s linear infinite' : undefined }}
            />
            <div className={`suzent-cube-scene relative h-20 w-20 ${error ? 'opacity-30' : ''}`}>
              <div
                className="suzent-cube absolute inset-0"
                style={error ? { animation: 'none', transform: 'rotateX(-20deg) rotateY(32deg)' } : undefined}
              >
                <div className="suzent-cube-face" style={{ transform: 'translateZ(40px)' }} />
                <div className="suzent-cube-face" style={{ transform: 'rotateY(180deg) translateZ(40px)', opacity: .72 }} />
                <div className="suzent-cube-face" style={{ transform: 'rotateY(90deg) translateZ(40px)', opacity: .86 }} />
                <div className="suzent-cube-face" style={{ transform: 'rotateY(-90deg) translateZ(40px)', opacity: .58 }} />
                <div className="suzent-cube-face" style={{ transform: 'rotateX(90deg) translateZ(40px)', opacity: .92 }} />
                <div className="suzent-cube-face" style={{ transform: 'rotateX(-90deg) translateZ(40px)', opacity: .5 }} />
              </div>
            </div>
          </div>
          <p className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.32em] text-neutral-500">
            {t('app.systemIdentity')}
          </p>
          <h1 className="mb-3 text-3xl font-brutal font-black uppercase tracking-[-0.035em] text-brutal-black">
            {error ? t('app.backendErrorTitle') : t('app.initializing')}
          </h1>
          <div className="mb-10 min-h-5 max-w-xs">
            <p className="text-sm font-medium leading-5 text-neutral-500">
              {error || setupStep || t('app.connectingToCore')}
            </p>
          </div>
          {error ? (
            onRetry ? (
              <button
                onClick={onRetry}
                className="border border-brutal-black bg-brutal-black px-6 py-3 text-xs font-bold uppercase tracking-[0.14em] text-white transition-colors hover:bg-white hover:text-brutal-black"
              >
                {t('common.retry')}
              </button>
            ) : null
          ) : hasMeasuredProgress ? (
            <div
              className="w-full"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-neutral-500">
                <span>{t('app.systemStartup')}</span>
                <span className="tabular-nums">{progress.toString().padStart(2, '0')}%</span>
              </div>
              <div className="relative h-px w-full overflow-hidden bg-neutral-300">
                <div
                  className="absolute inset-y-0 left-0 bg-brutal-black transition-[width] duration-700 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          ) : (
            <div
              className="w-full"
              role="progressbar"
              aria-label={t('app.connectingToCore')}
            >
              <div className="mb-2 text-left font-mono text-[10px] uppercase tracking-[0.16em] text-neutral-500">
                {t('app.systemStartup')}
              </div>
              <div className="relative h-px w-full overflow-hidden bg-neutral-300">
                <div
                  className="suzent-indeterminate-progress absolute inset-y-0 bg-brutal-black"
                  style={{ animation: 'suzentIndeterminateProgress 1.8s cubic-bezier(.65, 0, .35, 1) infinite' }}
                />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
