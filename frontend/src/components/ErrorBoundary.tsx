import React from 'react';
import { RobotAvatar } from './chat/RobotAvatar';
import { getInitialLocale, tForLocale } from '../i18n';

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log the error to console for debugging
    console.error('React Error Boundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      const locale = getInitialLocale();
      const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);

      // Return fallback UI or default error message
      return this.props.fallback || (
        <div className="w-full min-h-screen bg-neutral-100 dark:bg-zinc-900 p-4 sm:p-6 md:p-8 overflow-auto">
          <div className="mx-auto w-full max-w-5xl bg-white dark:bg-zinc-950 border-3 border-brutal-black shadow-brutal animate-brutal-shake p-4 sm:p-6 md:p-8">
            <div className="flex flex-col items-center text-center">
              <div className="w-16 h-16 mb-4 text-brutal-red">
                <RobotAvatar variant="shaker" />
              </div>
              <div className="text-brutal-red text-lg font-brutal uppercase mb-2">
                {t('errorBoundary.systemFailure')}
              </div>
              <div className="text-brutal-black dark:text-neutral-100 text-sm mb-4 font-mono break-words max-w-full">
                {this.state.error?.message || t('errorBoundary.unexpected')}
              </div>
              <button
                className="px-4 py-2 bg-brutal-red text-white border-2 border-brutal-black font-bold uppercase hover:bg-red-600 shadow-[2px_2px_0_0_#000] brutal-btn"
                onClick={() => this.setState({ hasError: false, error: undefined })}
              >
                {t('errorBoundary.reboot')}
              </button>
            </div>

            <details className="mt-4 text-xs text-brutal-black dark:text-neutral-100 w-full">
              <summary className="cursor-pointer font-bold uppercase">{t('errorBoundary.details')}</summary>
              <pre className="mt-2 p-2 bg-neutral-100 dark:bg-zinc-900 border-2 border-brutal-black overflow-x-auto overflow-y-auto max-h-[50vh] font-mono text-[10px] whitespace-pre-wrap break-words">
                {this.state.error?.stack}
              </pre>
            </details>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}