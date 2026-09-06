import React, { useEffect, useRef, useState } from 'react';
import { getApiBase } from '../../lib/api';
import { connectBrowserPreview } from '../../lib/browserPreview';

import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import {
  ArrowTopRightOnSquareIcon,
  CursorArrowRaysIcon,
  PlayIcon,
  StopIcon,
} from '@heroicons/react/24/outline';

export interface BrowserViewProps {
  visible?: boolean;
  onStreamActive?: (isActive: boolean) => void;
}

export function BrowserView({ onStreamActive, visible = true }: BrowserViewProps) {
  const { t } = useI18n();
  const [status, setStatus] = useState<'connected' | 'disconnected' | 'connecting'>('disconnected');
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [isControlling, setIsControlling] = useState(false);
  const [details, setDetails] = useState<{
    mode: 'managed' | 'existing' | 'extension';
    browser: string;
    connected: boolean;
    selected: boolean;
    title: string | null;
  } | null>(null);
  const [previewChoice, setPreviewChoice] = useState<{ mode: string; enabled: boolean } | null>(
    null
  );
  const [documentVisible, setDocumentVisible] = useState(document.visibilityState === 'visible');
  const [actionError, setActionError] = useState(false);
  const previewEnabled =
    previewChoice?.mode === details?.mode
      ? previewChoice?.enabled === true
      : details?.mode === 'managed';
  const watching = visible && documentVisible;
  const streaming = watching && !!details && previewEnabled;
  const supportsControl = details?.mode === 'managed';
  const controlActive = supportsControl && isControlling;

  useEffect(() => {
    const update = (): void => setDocumentVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);

  useEffect(() => {
    if (!watching) {
      setDetails(null);
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async (): Promise<void> => {
      try {
        const response = await fetch(`${getApiBase()}/browser/status`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error();
        const next = await response.json();
        if (!controller.signal.aborted) setDetails(next);
      } catch {
        if (!controller.signal.aborted) setDetails(null);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void refresh(), 5000);
      }
    };
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [watching]);

  const showTab = async (): Promise<void> => {
    setActionError(false);
    try {
      const response = await fetch(`${getApiBase()}/browser/status`, {
        method: 'POST',
        headers: { 'X-Suzent-Browser-Setup': '1' },
      });
      if (!response.ok) throw new Error();
    } catch {
      setActionError(true);
    }
  };

  const wsRef = useRef<WebSocket | null>(null);
  const frameSize = useRef<{ width: number; height: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => onStreamActive?.(false), [onStreamActive]);

  // Notify parent about stream status
  useEffect(() => {
    onStreamActive?.(streaming && !!imageSrc);
  }, [imageSrc, streaming, onStreamActive]);

  useEffect(() => {
    setImageSrc(null);
    setIsControlling(false);
    frameSize.current = null;
    setStatus('disconnected');
    if (!streaming) return;
    const url = new URL(getApiBase());
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/ws/browser';
    url.searchParams.set('mode', details!.mode);
    return connectBrowserPreview(
      url.toString(),
      (socket) => {
        wsRef.current = socket;
      },
      (next) => {
        setStatus(next);
        if (next === 'disconnected') {
          setImageSrc(null);
          setIsControlling(false);
        }
      },
      (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'frame' && msg.data) {
          frameSize.current =
            Number.isFinite(msg.width) &&
            Number.isFinite(msg.height) &&
            msg.width > 0 &&
            msg.height > 0
              ? { width: msg.width, height: msg.height }
              : null;
          setImageSrc(`data:image/jpeg;base64,${msg.data}`);
        }
        if (msg.type === 'reset') {
          frameSize.current = null;
          setImageSrc(null);
          setIsControlling(false);
        }
      }
    );
  }, [streaming, details?.mode]);

  const toggleControl = () => {
    if (!supportsControl) return;
    const newState = !isControlling;
    setIsControlling(newState);
    if (newState) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };

  // Helper to check if control actions are allowed
  const canControl = () => wsRef.current && status === 'connected' && controlActive;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!canControl()) return;

    // Exit on Escape
    if (e.key === 'Escape') {
      setIsControlling(false);
      return;
    }

    e.preventDefault();

    // Handle special keys vs typing
    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      wsRef.current!.send(
        JSON.stringify({
          type: 'type',
          text: e.key,
        })
      );
    } else {
      wsRef.current!.send(
        JSON.stringify({
          type: 'key',
          key: e.key,
        })
      );
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    if (!canControl()) return;

    // Throttle? For now direct send, but maybe limit rate if needed
    wsRef.current!.send(
      JSON.stringify({
        type: 'scroll',
        dx: e.deltaX,
        dy: e.deltaY,
      })
    );
  };

  const mouseRef = useRef<{ isDown: boolean; lastMove: number }>({ isDown: false, lastMove: 0 });

  const getCoords = (e: React.MouseEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const rect = img.getBoundingClientRect();
    const scaleX = (frameSize.current?.width ?? img.naturalWidth) / rect.width;
    const scaleY = (frameSize.current?.height ?? img.naturalHeight) / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!canControl()) return;
    mouseRef.current.isDown = true;
    const { x, y } = getCoords(e);

    wsRef.current!.send(JSON.stringify({ type: 'mousedown', x, y }));

    // Keep focus
    inputRef.current?.focus();
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!canControl()) return;
    mouseRef.current.isDown = false;
    const { x, y } = getCoords(e);
    wsRef.current!.send(JSON.stringify({ type: 'mouseup', x, y }));
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!canControl()) return;

    // Always send move if controlling, allowing hover?
    // Or only when down for drag? User wants "select text", implies drag.
    // But to select, you move mouse.
    // Sending ALL moves is heavy. Let's send moves if down OR throttled hover?
    // Let's settle on: Throttle all moves to 50ms.

    const now = Date.now();
    if (now - mouseRef.current.lastMove < 50) return; // 20fps cap

    mouseRef.current.lastMove = now;
    const { x, y } = getCoords(e);
    wsRef.current!.send(JSON.stringify({ type: 'mousemove', x, y }));
  };

  return (
    <div
      className="flex flex-col h-full min-h-0 min-w-0 bg-neutral-100 dark:bg-zinc-900"
      ref={containerRef}
    >
      <div className="px-3 pt-3 pb-3 bg-white dark:bg-zinc-800 border-b-2 border-brutal-black shrink-0">
        <div className="flex flex-wrap items-center gap-2 pb-3 text-xs">
          <div className="flex-1 min-w-0 basis-32">
            <p className="flex items-center gap-2 font-bold">
              <span
                aria-hidden="true"
                className={`h-2 w-2 shrink-0 rounded-full ${details?.connected ? 'bg-green-500' : 'bg-neutral-400'}`}
              />
              <span className="min-w-0 break-words">
                {details?.browser === 'msedge'
                  ? 'Edge'
                  : details?.browser === 'chromium'
                    ? 'Chromium'
                    : details?.browser === 'chrome'
                      ? 'Chrome'
                      : (details?.browser ?? t('browser.title'))}{' '}
                · {t(`browser.status.${details?.connected ? 'connected' : 'disconnected'}`)}
              </span>
            </p>
            <p
              className="mt-1 truncate text-neutral-500 dark:text-zinc-400"
              title={details?.title ?? undefined}
            >
              {details?.title ?? t('browser.noSelectedTab')}
            </p>
          </div>
          <BrutalButton
            size="xs"
            variant="ghost"
            className="shrink-0"
            disabled={!details?.selected}
            onClick={() => void showTab()}
          >
            <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {t('browser.showTab')}
          </BrutalButton>
        </div>
        <div className="flex flex-wrap items-stretch gap-2 pr-0.5 pb-0.5">
          <BrutalButton
            size="sm"
            className="min-w-0 flex-1 basis-36 break-words"
            aria-pressed={previewEnabled}
            disabled={!details}
            onClick={() => setPreviewChoice({ mode: details!.mode, enabled: !previewEnabled })}
          >
            {previewEnabled ? (
              <StopIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <PlayIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            {t(previewEnabled ? 'browser.stopPreview' : 'browser.livePreview')}
          </BrutalButton>
          {supportsControl && status === 'connected' && imageSrc && (
            <BrutalButton
              onClick={toggleControl}
              size="sm"
              variant={isControlling ? 'danger' : 'warning'}
              aria-pressed={isControlling}
              className="min-w-0 flex-1 basis-36 break-words"
            >
              <CursorArrowRaysIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {t(isControlling ? 'browser.exitControl' : 'browser.takeControl')}
            </BrutalButton>
          )}
        </div>
      </div>

      {actionError && (
        <p role="alert" className="px-3 text-xs">
          {t('browser.showTabError')}
        </p>
      )}
      <div
        className={`relative flex-1 min-h-0 min-w-0 overflow-hidden flex items-center justify-center bg-neutral-100 dark:bg-zinc-900 ${controlActive ? 'ring-4 ring-inset ring-green-500/50' : ''}`}
      >
        {/* Hidden input for keyboard capture */}
        {supportsControl && (
          <input
            ref={inputRef}
            type="text"
            className="absolute opacity-0 w-0 h-0"
            onKeyDown={handleKeyDown}
            autoFocus={controlActive}
          />
        )}

        {imageSrc ? (
          <div
            className="relative group w-full h-full min-h-0 flex items-start justify-center"
            onWheel={handleWheel}
          >
            <img
              src={imageSrc}
              className="block max-w-full max-h-full w-auto h-auto shadow-sm cursor-default"
              onMouseDown={handleMouseDown}
              onMouseUp={handleMouseUp}
              onMouseMove={handleMouseMove}
              alt={t('browser.streamAlt')}
              draggable={false}
            />

            {/* Overlay when NOT controlling but connected */}
            {supportsControl && !isControlling && status === 'connected' && (
              <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center backdrop-blur-[1px]">
                <BrutalButton
                  onClick={toggleControl}
                  className="uppercase tracking-widest text-sm shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
                >
                  {t('browser.takeControl')}
                </BrutalButton>
              </div>
            )}

            {/* Visual indicator for control mode */}
            {controlActive && (
              <div className="absolute top-4 right-4 bg-green-500 text-white text-[10px] font-bold px-2 py-1 uppercase tracking-wider shadow-lg pointer-events-none animate-pulse">
                {t('browser.liveControlActive')}
              </div>
            )}
          </div>
        ) : (
          <div className="text-neutral-400 dark:text-zinc-500 text-[11px] text-center font-mono">
            <p className="mb-2 font-bold uppercase tracking-widest">
              {t(previewEnabled ? 'browser.waitingForStream' : 'browser.previewOff')}
            </p>
            {status === 'connected' && (
              <p className="text-[10px] opacity-70">{t('browser.executeHint')}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
