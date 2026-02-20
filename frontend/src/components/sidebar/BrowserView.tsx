import React, { useEffect, useRef, useState } from 'react';
import { API_BASE } from '../../lib/api';
import { useI18n } from '../../i18n';

export function BrowserView() {
    const { t } = useI18n();
    const [status, setStatus] = useState<'connected' | 'disconnected' | 'connecting'>('disconnected');
    const [imageSrc, setImageSrc] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);

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
        const url = new URL(API_BASE);
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

    const handleInteraction = (e: React.MouseEvent<HTMLImageElement>) => {
        if (!wsRef.current || status !== 'connected') return;

        const img = e.currentTarget;
        const rect = img.getBoundingClientRect();

        // Calculate scale if image is resized via CSS
        const scaleX = img.naturalWidth / rect.width;
        const scaleY = img.naturalHeight / rect.height;

        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        wsRef.current.send(JSON.stringify({
            type: 'click',
            x,
            y
        }));
    };

    return (
        <div className="flex flex-col h-full bg-neutral-100" ref={containerRef}>
            <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
                <span className="font-bold text-xs uppercase text-gray-500">
                    {t('browser.streamTitle')}
                </span>
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${status === 'connected' ? 'bg-green-500' :
                            status === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
                        }`} />
                    <span className="text-xs font-mono text-gray-400 capitalize">
                        {status === 'connected' ? t('browser.status.connected') : status === 'connecting' ? t('browser.status.connecting') : t('browser.status.disconnected')}
                    </span>
                </div>
            </div>

            <div className="flex-1 overflow-auto flex items-center justify-center p-4">
                {imageSrc ? (
                    <img
                        src={imageSrc}
                        className="max-w-full shadow-lg border border-gray-300 cursor-crosshair"
                        onClick={handleInteraction}
                        alt={t('browser.streamAlt')}
                    />
                ) : (
                    <div className="text-gray-400 text-sm text-center">
                        <p>{t('browser.waiting')}</p>
                        {status === 'connected' && <p className="text-xs mt-2">{t('browser.hiddenHint')}</p>}
                    </div>
                )}
            </div>
        </div>
    );
}
