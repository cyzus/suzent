import React, { useEffect, useRef, useState } from 'react';
import { getApiBase } from '../../lib/api';
import { useI18n } from '../../i18n';

import { BrutalButton } from '../BrutalButton';




export interface BrowserViewProps {
    onStreamActive?: (isActive: boolean) => void;
}

export function BrowserView({ onStreamActive }: BrowserViewProps) {
    const { t } = useI18n();
    const [status, setStatus] = useState<'connected' | 'disconnected' | 'connecting'>('disconnected');
    const [imageSrc, setImageSrc] = useState<string | null>(null);
    const [isControlling, setIsControlling] = useState(false);
    // Remove headerHover as we can rely on group-hover usually, but keeping for overlay logic if needed

    const wsRef = useRef<WebSocket | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Notify parent about stream status
    useEffect(() => {
        onStreamActive?.(!!imageSrc);
    }, [imageSrc, onStreamActive]);

    useEffect(() => {
        connect();
        return () => {
            cleanup();
        };
    }, []);

    const cleanup = () => {
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
    };

    const connect = () => {
        if (wsRef.current) return;

        setStatus('connecting');
        // Convert API_BASE (http) to ws
        const url = new URL(getApiBase());
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        url.pathname = '/ws/browser';

        const ws = new WebSocket(url.toString());

        ws.onopen = () => {
            setStatus('connected');
            console.log('Browser WS Connected');
        };

        ws.onclose = () => {
            setStatus('disconnected');
            wsRef.current = null;
            // Simple reconnect logic?
            setTimeout(connect, 3000);
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'frame' && msg.data) {
                // msg.data is base64
                setImageSrc(`data:image/jpeg;base64,${msg.data}`);
            }
        };

        wsRef.current = ws;
    };

    const toggleControl = () => {
        const newState = !isControlling;
        setIsControlling(newState);
        if (newState) {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    };

    // Helper to check if control actions are allowed
    const canControl = () => wsRef.current && status === 'connected' && isControlling;

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
            wsRef.current!.send(JSON.stringify({
                type: 'type',
                text: e.key
            }));
        } else {
            wsRef.current!.send(JSON.stringify({
                type: 'key',
                key: e.key
            }));
        }
    };

    const handleWheel = (e: React.WheelEvent) => {
        if (!canControl()) return;

        // Throttle? For now direct send, but maybe limit rate if needed
        wsRef.current!.send(JSON.stringify({
            type: 'scroll',
            dx: e.deltaX,
            dy: e.deltaY
        }));
    };

    const mouseRef = useRef<{ isDown: boolean, lastMove: number }>({ isDown: false, lastMove: 0 });

    const getCoords = (e: React.MouseEvent<HTMLImageElement>) => {
        const img = e.currentTarget;
        const rect = img.getBoundingClientRect();
        const scaleX = img.naturalWidth / rect.width;
        const scaleY = img.naturalHeight / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY
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
        <div className="flex flex-col h-full bg-neutral-100" ref={containerRef}>
            <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
                <span className="font-bold text-xs uppercase text-gray-500">
                    {t('browser.streamTitle')}
                </span>
                <div className="flex items-center gap-4">
                    {status === 'connected' && imageSrc && (
                        <BrutalButton
                            onClick={toggleControl}
                            size="sm"
                            variant={isControlling ? 'danger' : 'default'}
                            className="text-[10px] py-0.5 h-6"
                        >
                            {isControlling ? t('browser.exitControl') : t('browser.takeControl')}
                        </BrutalButton>
                    )}
                    <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${status === 'connected' ? 'bg-green-500' :
                            status === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
                            }`} />
                        <span className="text-xs font-mono text-gray-400 capitalize">
                            {status === 'connected'
                                ? t('browser.status.connected')
                                : status === 'connecting'
                                    ? t('browser.status.connecting')
                                    : t('browser.status.disconnected')}
                        </span>
                    </div>
                </div>
            </div>

            <div className={`relative flex-1 overflow-hidden flex items-center justify-center bg-neutral-100 ${isControlling ? 'ring-4 ring-inset ring-green-500/50' : ''}`}>
                {/* Hidden input for keyboard capture */}
                <input
                    ref={inputRef}
                    type="text"
                    className="absolute opacity-0 w-0 h-0"
                    onKeyDown={handleKeyDown}
                    autoFocus={isControlling}
                />

                {imageSrc ? (
                    <div
                        className="relative group max-w-full max-h-full flex items-center justify-center"
                        onWheel={handleWheel}
                    >
                        <img
                            src={imageSrc}
                            className="max-w-full max-h-full shadow-2xl cursor-default"
                            onMouseDown={handleMouseDown}
                            onMouseUp={handleMouseUp}
                            onMouseMove={handleMouseMove}
                            alt={t('browser.streamAlt')}
                            draggable={false}
                        />



                        {/* Overlay when NOT controlling but connected */}
                        {!isControlling && status === 'connected' && (
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
                        {isControlling && (
                            <div className="absolute top-4 right-4 bg-green-500 text-white text-[10px] font-bold px-2 py-1 uppercase tracking-wider shadow-lg pointer-events-none animate-pulse">
                                {t('browser.liveControlActive')}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="text-gray-500 text-sm text-center font-mono">
                        <p className="mb-2">{t('browser.waitingForStream')}</p>
                        {status === 'connected' &&
                            <p className="text-xs text-gray-600 opacity-70">{t('browser.executeHint')}</p>
                        }
                    </div>
                )}
            </div>
        </div>
    );
}
