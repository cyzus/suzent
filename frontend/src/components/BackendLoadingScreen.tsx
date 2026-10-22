import React from 'react';
import { invoke } from '@tauri-apps/api/core';

import { getInitialLocale, tForLocale } from '../i18n';
import { isDesktop } from '../lib/runtime';
import { detectDesktopPlatform } from '../lib/titleBarPlatform';
import { TitleBar } from './TitleBar';

interface BackendLoadingScreenProps {
  error?: string | null;
  onRetry?: () => void | Promise<void>;
  status?: string;
  progressHint?: number;
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

export function BackendLoadingScreen({
  error,
  onRetry,
  status,
  progressHint = 0,
}: BackendLoadingScreenProps): React.ReactElement {
  const locale = getInitialLocale();
  const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);
  const [setupStep, setSetupStep] = React.useState<string | null>(null);
  const [progress, setProgress] = React.useState(0);
  const [elapsedSeconds, setElapsedSeconds] = React.useState(0);

  const [recovering, setRecovering] = React.useState(false);
  const [recoveryError, setRecoveryError] = React.useState<string | null>(null);
  const recoveryPending = React.useRef(false);

  async function handleRecovery(): Promise<void> {
    if (recoveryPending.current) return;
    recoveryPending.current = true;
    setRecovering(true);
    setRecoveryError(null);
    try {
      if (onRetry) {
        await onRetry();
        recoveryPending.current = false;
        setRecovering(false);
      } else if (isDesktop()) {
        await invoke('restart_app');
      } else {
        window.location.reload();
      }
    } catch {
      setRecoveryError(t('app.recoveryFailed'));
      recoveryPending.current = false;
      setRecovering(false);
    }
  }

  React.useEffect(() => {
    if (!isDesktop()) return;
    if (detectDesktopPlatform(navigator.userAgent, navigator.platform) !== 'macos') return;
    void invoke('set_startup_window_controls', { enabled: true }).catch(console.error);
    return () => {
      void invoke('set_startup_window_controls', { enabled: false }).catch(console.error);
    };
  }, []);

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
    if (error) return;
    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [error]);

  const effectiveProgress = Math.max(progress, progressHint);
  const hasMeasuredProgress = effectiveProgress > 0;

  return (
    <div className="flex h-screen w-screen flex-col bg-neutral-50 dark:bg-zinc-900 text-brutal-black dark:text-white font-sans text-center overflow-hidden">
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
          .suzent-indeterminate-progress {
            animation: none !important;
          }
          .suzent-indeterminate-progress {
            left: 0;
            width: 32%;
          }
        }
      `}</style>
      {isDesktop() && <TitleBar startup />}
      {isDesktop() && (
        <div
          className={
            detectDesktopPlatform(navigator.userAgent, navigator.platform) === 'windows'
              ? 'h-12 shrink-0'
              : 'h-8 shrink-0'
          }
          data-tauri-drag-region
        />
      )}
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-8">
        <main className="relative flex w-full max-w-sm flex-col items-center">
          <div
            className="relative mb-10 flex h-40 w-40 items-center justify-center"
            aria-hidden="true"
          >
            <div
              className="suzent-orbit absolute h-40 w-40 rounded-full border border-neutral-300"
              style={{ animation: !error ? 'suzentOrbitTurn 12s linear infinite' : undefined }}
            >
              <span className="absolute -right-1 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-black" />
            </div>
            <div
              className="suzent-orbit-reverse absolute h-[7.75rem] w-[7.75rem] rounded-full border border-dashed border-neutral-400/70"
              style={{
                animation: !error ? 'suzentOrbitTurnReverse 18s linear infinite' : undefined,
              }}
            />
            <div className={`suzent-cube-scene relative h-20 w-20 ${error ? 'opacity-30' : ''}`}>
              <div
                className="suzent-cube absolute inset-0"
                style={
                  error
                    ? { animation: 'none', transform: 'rotateX(-20deg) rotateY(32deg)' }
                    : undefined
                }
              >
                <div className="suzent-cube-face" style={{ transform: 'translateZ(40px)' }} />
                <div
                  className="suzent-cube-face"
                  style={{ transform: 'rotateY(180deg) translateZ(40px)', opacity: 0.72 }}
                />
                <div
                  className="suzent-cube-face"
                  style={{ transform: 'rotateY(90deg) translateZ(40px)', opacity: 0.86 }}
                />
                <div
                  className="suzent-cube-face"
                  style={{ transform: 'rotateY(-90deg) translateZ(40px)', opacity: 0.58 }}
                />
                <div
                  className="suzent-cube-face"
                  style={{ transform: 'rotateX(90deg) translateZ(40px)', opacity: 0.92 }}
                />
                <div
                  className="suzent-cube-face"
                  style={{ transform: 'rotateX(-90deg) translateZ(40px)', opacity: 0.5 }}
                />
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
              {error || setupStep || status || t('app.connectingToCore')}
            </p>
            {!error && (
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-neutral-400">
                {t('app.startupElapsed', { seconds: String(elapsedSeconds) })}
              </p>
            )}
          </div>
          {error ? null : hasMeasuredProgress ? (
            <div
              className="w-full"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={effectiveProgress}
            >
              <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-neutral-500">
                <span>{t('app.systemStartup')}</span>
                <span className="tabular-nums">
                  {effectiveProgress.toString().padStart(2, '0')}%
                </span>
              </div>
              <div className="relative h-px w-full overflow-hidden bg-neutral-300">
                <div
                  className="absolute inset-y-0 left-0 bg-brutal-black transition-[width] duration-700 ease-out"
                  style={{ width: `${effectiveProgress}%` }}
                />
              </div>
            </div>
          ) : (
            <div className="w-full" role="progressbar" aria-label={t('app.connectingToCore')}>
              <div className="mb-2 text-left font-mono text-[10px] uppercase tracking-[0.16em] text-neutral-500">
                {t('app.systemStartup')}
              </div>
              <div className="relative h-px w-full overflow-hidden bg-neutral-300">
                <div
                  className="suzent-indeterminate-progress absolute inset-y-0 bg-brutal-black"
                  style={{
                    animation:
                      'suzentIndeterminateProgress 1.8s cubic-bezier(.65, 0, .35, 1) infinite',
                  }}
                />
              </div>
            </div>
          )}
          {error && (
            <div className="mt-8 flex flex-col items-center gap-3">
              <button
                type="button"
                onClick={() => void handleRecovery()}
                disabled={recovering}
                className="border border-neutral-400 bg-transparent px-5 py-2.5 text-xs font-bold tracking-wide text-neutral-700 transition-colors hover:border-black hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 disabled:cursor-wait disabled:opacity-50"
              >
                {t(
                  recovering
                    ? 'app.recovering'
                    : isDesktop()
                      ? 'app.recoverStartup'
                      : 'app.reconnectStartup'
                )}
              </button>
              <p className="max-w-xs text-xs leading-5 text-neutral-500">
                {t(isDesktop() ? 'app.recoveryHintDesktop' : 'app.recoveryHintWeb')}
              </p>
              {recoveryError && (
                <p role="alert" className="max-w-xs text-xs text-red-700">
                  {recoveryError}
                </p>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
