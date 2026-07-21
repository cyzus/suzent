import React, { useCallback, useEffect, useState } from 'react';
import QRCode from 'qrcode';

import { useI18n } from '../../i18n';
import {
    PairingRequest,
    SocialConfig,
    WeChatLoginSession,
    approvePairing,
    denyPairing,
    fetchPairings,
    pollWeChatLogin,
    startWeChatLogin,
} from '../../lib/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalOnOff } from '../BrutalOnOff';
import { SettingsHeader } from './SettingsHeader';
import { SettingsCard, SectionCardHeader, GridCard } from './SettingsCard';

interface McpServersData {
    urls: Record<string, string>;
    stdio: Record<string, any>;
    enabled: Record<string, boolean>;
}

interface SocialTabProps {
    socialConfig: SocialConfig;
    tools: string[];
    mcpServers: McpServersData | null;
    useCustomTools: boolean;
    useCustomMcp: boolean;
    onConfigChange: (config: SocialConfig) => void;
    onUseCustomToolsChange: (use: boolean) => void;
    onUseCustomMcpChange: (use: boolean) => void;
}

function buildWeChatQrImageSrc(content?: string | null): string | null {
    const trimmed = content?.trim();
    if (!trimmed) return null;

    if (trimmed.startsWith('data:image/')) return trimmed;

    if (trimmed.startsWith('<svg') || trimmed.startsWith('<?xml') || trimmed.includes('<svg')) {
        return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(trimmed)}`;
    }

    const compact = trimmed.replace(/\s+/g, '');
    if (!/^[A-Za-z0-9+/=]+$/.test(compact)) return null;

    let mime = 'image/png';
    if (compact.startsWith('/9j/')) mime = 'image/jpeg';
    if (compact.startsWith('R0lGOD')) mime = 'image/gif';
    if (compact.startsWith('PHN2Zy')) mime = 'image/svg+xml';

    return `data:${mime};base64,${compact}`;
}

function getWeChatQrUrl(login?: WeChatLoginSession | null): string | null {
    const explicitUrl = login?.qrcode_url?.trim();
    if (explicitUrl) return explicitUrl;

    const content = login?.qrcode_img_content?.trim();
    if (content?.startsWith('http://') || content?.startsWith('https://')) {
        return content;
    }
    return null;
}

function getWeChatQrGenerationContent(login?: WeChatLoginSession | null): string | null {
    const content = login?.qrcode_img_content?.trim();
    if (content?.startsWith('http://') || content?.startsWith('https://')) {
        return content;
    }
    return getWeChatQrUrl(login);
}

export function SocialTab({
    socialConfig,
    tools,
    mcpServers,
    useCustomTools,
    useCustomMcp,
    onConfigChange,
    onUseCustomToolsChange,
    onUseCustomMcpChange,
}: SocialTabProps): React.ReactElement {
    const { t } = useI18n();

    const handshakeEnabled = !!(socialConfig.handshake as any)?.enabled;
    const [pairings, setPairings] = useState<PairingRequest[]>([]);
    const [pairingLoading, setPairingLoading] = useState(false);
    const [wechatLogin, setWechatLogin] = useState<WeChatLoginSession | null>(null);
    const [wechatLoginBusy, setWechatLoginBusy] = useState(false);
    const [wechatLoginError, setWechatLoginError] = useState<string | null>(null);
    const [wechatQrImageFailed, setWechatQrImageFailed] = useState(false);
    const [wechatGeneratedQrSrc, setWechatGeneratedQrSrc] = useState<string | null>(null);

    const refreshPairings = useCallback(async () => {
        if (!handshakeEnabled) return;
        setPairingLoading(true);
        try {
            setPairings(await fetchPairings());
        } finally {
            setPairingLoading(false);
        }
    }, [handshakeEnabled]);

    useEffect(() => {
        refreshPairings();
    }, [refreshPairings]);

    const handleApprove = async (token: string) => {
        await approvePairing(token);
        await refreshPairings();
    };

    const handleDeny = async (token: string) => {
        await denyPairing(token);
        await refreshPairings();
    };

    const beginWeChatLogin = async (baseUrl?: string) => {
        setWechatLoginBusy(true);
        setWechatLoginError(null);
        try {
            const session = await startWeChatLogin(baseUrl);
            setWechatQrImageFailed(false);
            setWechatLogin(session);
        } catch (error) {
            setWechatLoginError(error instanceof Error ? error.message : String(error));
        } finally {
            setWechatLoginBusy(false);
        }
    };

    useEffect(() => {
        if (!wechatLogin?.session_id) return;

        let cancelled = false;
        const interval = window.setInterval(async () => {
            try {
                const status = await pollWeChatLogin(wechatLogin.session_id);
                if (cancelled) return;
                setWechatQrImageFailed(false);
                setWechatLogin(status);

                if (status.status === 'confirmed' && status.bot_token) {
                    window.clearInterval(interval);
                    setWechatLogin(null);
                    setWechatLoginError(null);
                    const existing = (socialConfig.wechat as any) || {};
                    onConfigChange({
                        ...socialConfig,
                        wechat: {
                            ...existing,
                            enabled: true,
                            bot_token: status.bot_token,
                            base_url: status.base_url || existing.base_url,
                        },
                    });
                }
            } catch (error) {
                if (!cancelled) {
                    setWechatLoginError(error instanceof Error ? error.message : String(error));
                }
            }
        }, 2000);

        return () => {
            cancelled = true;
            window.clearInterval(interval);
        };
    }, [wechatLogin?.session_id, onConfigChange, socialConfig]);

    useEffect(() => {
        const qrSrc = buildWeChatQrImageSrc(wechatLogin?.qrcode_img_content);
        const qrContent = qrSrc ? null : getWeChatQrGenerationContent(wechatLogin);
        let cancelled = false;
        setWechatGeneratedQrSrc(null);

        if (!qrContent) return;

        QRCode.toDataURL(qrContent, {
            errorCorrectionLevel: 'M',
            margin: 1,
            width: 256,
        })
            .then((dataUrl: string) => {
                if (!cancelled) setWechatGeneratedQrSrc(dataUrl);
            })
            .catch((error: unknown) => {
                if (!cancelled) {
                    setWechatLoginError(error instanceof Error ? error.message : String(error));
                }
            });

        return () => {
            cancelled = true;
        };
    }, [wechatLogin?.qrcode_img_content, wechatLogin?.qrcode_url]);

    const renderWeChatAuthPanel = (platformConfig: any): React.ReactElement => {
        const hasToken = !!platformConfig.bot_token && platformConfig.bot_token !== '********';
        const qrSrc = buildWeChatQrImageSrc(wechatLogin?.qrcode_img_content);
        const qrUrl = getWeChatQrUrl(wechatLogin);
        const displayQrSrc = qrSrc || wechatGeneratedQrSrc;

        return (
            <div className="space-y-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 p-3">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="text-xs font-black uppercase text-neutral-900 dark:text-neutral-100">{t('settings.social.wechatAuthTitle')}</div>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">{hasToken ? t('settings.social.wechatConnected') : t('settings.social.wechatAuthDesc')}</p>
                    </div>
                    <button
                        onClick={() => beginWeChatLogin(platformConfig.base_url)}
                        disabled={wechatLoginBusy}
                        className="shrink-0 px-3 py-2 text-xs font-bold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600 disabled:opacity-50 brutal-btn"
                    >
                        {wechatLoginBusy ? t('settings.social.wechatStarting') : t('settings.social.wechatLogin')}
                    </button>
                </div>

                {wechatLogin && (
                    <div className="flex flex-col sm:flex-row gap-3 items-start">
                        {displayQrSrc && !wechatQrImageFailed ? (
                            <img
                                src={displayQrSrc}
                                alt={t('settings.social.wechatQrAlt')}
                                onError={() => setWechatQrImageFailed(true)}
                                className="w-40 h-40 border-2 border-brutal-black bg-white object-contain"
                            />
                        ) : qrUrl ? (
                            <a
                                href={qrUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="w-40 min-h-24 border-2 border-brutal-black bg-white dark:bg-zinc-800 p-3 text-xs font-mono break-all text-brutal-blue"
                            >
                                {qrUrl}
                            </a>
                        ) : (
                            <div className="w-40 min-h-24 border-2 border-brutal-black bg-white dark:bg-zinc-800 p-3 text-xs font-mono break-all">
                                {wechatLogin.qrcode}
                            </div>
                        )}
                        <div className="space-y-1 text-xs font-mono text-neutral-600 dark:text-neutral-400">
                            <div>{t('settings.social.wechatWaiting')}</div>
                            <div>{t('settings.social.wechatStatus')}: {wechatLogin.status}</div>
                        </div>
                    </div>
                )}

                {wechatLoginError && (
                    <div className="border-2 border-brutal-red bg-red-50 dark:bg-red-950/30 p-2 text-xs font-mono text-brutal-red dark:text-red-300">
                        {wechatLoginError}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="space-y-6">
            <SettingsHeader title={t('settings.social.title')} subtitle={t('settings.social.subtitle')} />

            <SettingsCard>
                <SectionCardHeader
                    iconTone="black"
                    icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>}
                    title={t('settings.social.generalSettingsTitle')}
                    description={t('settings.social.generalSettingsDesc')}
                />

                <div className="space-y-4">
                    <div className="space-y-2">
                        <label className="text-sm font-bold uppercase text-neutral-800 dark:text-neutral-200">
                            {t('settings.social.globalAllowedUsers')}
                        </label>
                        <input
                            type="text"
                            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                            value={(socialConfig.allowed_users || []).join(', ')}
                            onChange={(e) => onConfigChange({ ...socialConfig, allowed_users: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                            placeholder={t('settings.social.allowedUsersPlaceholder')}
                        />
                    </div>
                </div>
            </SettingsCard>

            {/* Agent Capabilities Card */}
            <SettingsCard>
                <SectionCardHeader
                    iconTone="blue"
                    icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>}
                    title={t('settings.social.agentCapabilitiesTitle')}
                    description={t('settings.social.agentCapabilitiesDesc')}
                />

                <div className="space-y-6">
                    {/* Memory Toggle */}
                    <div className="flex items-center justify-between">
                        <label className="text-sm font-bold uppercase text-neutral-800 dark:text-neutral-200">{t('settings.social.enableMemoryTools')}</label>
                        <BrutalOnOff
                            checked={socialConfig.memory_enabled !== false}
                            onChange={(checked) => onConfigChange({ ...socialConfig, memory_enabled: checked })}
                        />
                    </div>

                    {/* Tools Section */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-bold uppercase text-neutral-800 dark:text-neutral-200">{t('settings.social.tools')}</label>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => {
                                        onUseCustomToolsChange(false);
                                        onConfigChange({ ...socialConfig, tools: null });
                                    }}
                                    className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${!useCustomTools ? 'bg-brutal-black text-white' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}`}
                                >
                                    {t('settings.social.allTools')}
                                </button>
                                <button
                                    onClick={() => {
                                        onUseCustomToolsChange(true);
                                        onConfigChange({ ...socialConfig, tools: socialConfig.tools || [] });
                                    }}
                                    className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${useCustomTools ? 'bg-brutal-black text-white' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}`}
                                >
                                    {t('settings.social.custom')}
                                </button>
                            </div>
                        </div>
                        {useCustomTools && (
                            <BrutalMultiSelect
                                variant="list"
                                value={socialConfig.tools || []}
                                onChange={(newVal) => onConfigChange({ ...socialConfig, tools: newVal })}
                                options={tools.map((t) => ({ value: t, label: t }))}
                                emptyMessage={t('settings.social.noToolsAvailable')}
                                dropdownClassName="max-h-48"
                            />
                        )}
                    </div>

                    {/* MCP Section */}
                    {mcpServers && Object.keys(mcpServers.urls).length + Object.keys(mcpServers.stdio).length > 0 && (
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <label className="text-sm font-bold uppercase text-neutral-800 dark:text-neutral-200">{t('settings.social.mcpServers')}</label>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => {
                                            onUseCustomMcpChange(false);
                                            onConfigChange({ ...socialConfig, mcp_enabled: null });
                                        }}
                                        className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${!useCustomMcp ? 'bg-brutal-black text-white' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}`}
                                    >
                                        {t('settings.social.systemDefault')}
                                    </button>
                                    <button
                                        onClick={() => {
                                            onUseCustomMcpChange(true);
                                            onConfigChange({
                                                ...socialConfig,
                                                mcp_enabled: socialConfig.mcp_enabled || { ...mcpServers.enabled }
                                            });
                                        }}
                                        className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${useCustomMcp ? 'bg-brutal-black text-white' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}`}
                                    >
                                        {t('settings.social.custom')}
                                    </button>
                                </div>
                            </div>
                            {useCustomMcp && (
                                <div className="space-y-2 border-2 border-brutal-black p-3 bg-neutral-50 dark:bg-zinc-900">
                                    {[...Object.keys(mcpServers.urls), ...Object.keys(mcpServers.stdio)].map(name => (
                                        <div key={name} className="flex items-center justify-between gap-3">
                                            <span className="font-mono text-xs font-bold truncate">{name}</span>
                                            <BrutalOnOff
                                                size="sm"
                                                checked={socialConfig.mcp_enabled?.[name] ?? mcpServers.enabled[name] ?? true}
                                                onChange={(checked) => onConfigChange({
                                                    ...socialConfig,
                                                    mcp_enabled: { ...(socialConfig.mcp_enabled || {}), [name]: checked }
                                                })}
                                            />
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </SettingsCard>

            {/* Pairing / Handshake card — always shown */}
            <SettingsCard>
                <SectionCardHeader
                    iconTone="yellow"
                    icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>}
                    title={t('settings.social.pairingTitle')}
                    description={t('settings.social.pairingDesc')}
                    actions={
                        <>
                            {handshakeEnabled && (
                                <button
                                    onClick={refreshPairings}
                                    disabled={pairingLoading}
                                    className="px-3 py-2 text-xs font-bold uppercase border-2 border-brutal-black bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600 disabled:opacity-50 brutal-btn"
                                >
                                    {pairingLoading ? '…' : t('common.refresh')}
                                </button>
                            )}
                            <BrutalOnOff
                                checked={handshakeEnabled}
                                onChange={(checked) => onConfigChange({
                                    ...socialConfig,
                                    handshake: { ...(socialConfig.handshake as any || {}), enabled: checked },
                                })}
                            />
                        </>
                    }
                />

                {!handshakeEnabled && (
                    <div className="border-3 border-dashed border-neutral-300 dark:border-neutral-600 p-6 text-center">
                        <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">{t('settings.social.pairingDisabled')}</p>
                    </div>
                )}

                {handshakeEnabled && (pairings.length === 0 ? (
                    <div className="border-3 border-dashed border-neutral-300 dark:border-neutral-600 p-6 text-center">
                        <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">{t('settings.social.noPendingRequests')}</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {pairings.map((p) => (
                            <div key={p.token} className="border-2 border-brutal-black p-3 bg-neutral-50 dark:bg-zinc-900 flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-mono text-base font-black tracking-widest bg-brutal-yellow text-brutal-black border border-brutal-black px-2 py-0.5">{p.token}</span>
                                        <span className="text-xs font-bold uppercase bg-neutral-200 dark:bg-zinc-700 px-1">{p.platform}</span>
                                        <span className="font-mono text-sm font-bold">{p.sender_name}</span>
                                        <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400">{p.sender_id}</span>
                                    </div>
                                    {p.intro && (
                                        <p className="text-sm text-neutral-700 dark:text-neutral-300 mt-1 truncate">{p.intro}</p>
                                    )}
                                </div>
                                <div className="flex gap-2 shrink-0">
                                    <button
                                        onClick={() => handleApprove(p.token)}
                                        className="px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black bg-brutal-green text-brutal-black hover:brightness-110"
                                    >
                                        {t('settings.social.approve')}
                                    </button>
                                    <button
                                        onClick={() => handleDeny(p.token)}
                                        className="px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black bg-brutal-red text-white hover:brightness-110"
                                    >
                                        {t('settings.social.deny')}
                                    </button>
                                </div>
                            </div>
                        ))}
                        </div>
                ))}
            </SettingsCard>

            {/* Platform-specific cards */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
                {Object.entries(socialConfig).map(([key, value]) => {
                    if (key === 'allowed_users' || key === 'model' || key === 'memory_enabled' || key === 'tools' || key === 'mcp_enabled' || key === 'handshake') return null;
                    if (typeof value !== 'object' || value === null) return null;

                    const platformConfig = value as any;
                    const isEnabled = !!platformConfig.enabled;

                    return (
                        <GridCard
                            key={key}
                            title={key}
                            headerRight={
                                <BrutalOnOff
                                    checked={isEnabled}
                                    onChange={(checked) => onConfigChange({
                                        ...socialConfig,
                                        [key]: { ...platformConfig, enabled: checked }
                                    })}
                                />
                            }
                        >
                            <div className={`p-5 space-y-3 transition-opacity ${isEnabled ? '' : 'opacity-60'}`}>
                                {key === 'wechat' && renderWeChatAuthPanel(platformConfig)}

                                {Object.entries(platformConfig).map(([fieldKey, fieldVal]) => {
                                    if (fieldKey === 'enabled' || fieldKey === 'allowed_users') return null;

                                    const isSecret = fieldKey.includes('token') || fieldKey.includes('secret') || fieldKey.includes('key');

                                    return (
                                        <div key={fieldKey} className="space-y-1">
                                            <label className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 tracking-wider">
                                                {fieldKey.replace(/_/g, ' ')}
                                            </label>
                                            <input
                                                type={isSecret ? "password" : "text"}
                                                value={fieldVal as string}
                                                onChange={(e) => onConfigChange({
                                                    ...socialConfig,
                                                    [key]: { ...platformConfig, [fieldKey]: e.target.value }
                                                })}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                                            />
                                        </div>
                                    );
                                })}

                                <div className="space-y-1 mt-4 pt-3 border-t-2 border-dashed border-neutral-300 dark:border-zinc-600">
                                    <label className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 tracking-wider">
                                        {t('settings.social.allowedUsersSpecific')}
                                    </label>
                                    <input
                                        type="text"
                                        value={(platformConfig.allowed_users || []).join(', ')}
                                        onChange={(e) => onConfigChange({
                                            ...socialConfig,
                                            [key]: {
                                                ...platformConfig,
                                                allowed_users: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                                            }
                                        })}
                                        placeholder={t('settings.social.allowedUsersSpecificPlaceholder')}
                                        className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                                    />
                                </div>
                            </div>
                        </GridCard>
                    );
                })}
            </div>
        </div>
    );
}
