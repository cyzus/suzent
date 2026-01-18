import React from 'react';
import { RobotAvatar } from './chat/RobotAvatar';

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
      // Return fallback UI or default error message
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-64 p-8 bg-white border-3 border-brutal-black shadow-brutal animate-brutal-shake">
          <div className="w-16 h-16 mb-4 text-brutal-red">
            <RobotAvatar variant="shaker" />
          </div>
          <div className="text-brutal-red text-lg font-brutal uppercase mb-2">
            System Failure
          </div>
          <div className="text-brutal-black text-sm mb-4 text-center font-mono">
            {this.state.error?.message || 'An unexpected error occurred'}
          </div>
          <button
            className="px-4 py-2 bg-brutal-red text-white border-2 border-brutal-black font-bold uppercase hover:bg-red-600 shadow-brutal-sm active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
            onClick={() => this.setState({ hasError: false, error: undefined })}
          >
            Reboot System
          </button>
          <details className="mt-4 text-xs text-brutal-black w-full">
            <summary className="cursor-pointer font-bold uppercase">Error details</summary>
            <pre className="mt-2 p-2 bg-neutral-100 border-2 border-brutal-black overflow-auto font-mono text-[10px]">
              {this.state.error?.stack}
            </pre>
          </details>
        </div>
      );
    }

    return this.props.children;
  }
}