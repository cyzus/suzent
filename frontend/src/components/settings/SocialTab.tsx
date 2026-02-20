import React from 'react';

import { SocialConfig } from '../../lib/api';
import { useI18n } from '../../i18n';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalToggle } from '../BrutalToggle';

interface McpServersData {
    urls: Record<string, string>;
    stdio: Record<string, any>;
    enabled: Record<string, boolean>;
}

interface SocialTabProps {
    socialConfig: SocialConfig;
    models: string[];
    tools: string[];
    mcpServers: McpServersData | null;
    useCustomTools: boolean;
    useCustomMcp: boolean;
    onConfigChange: (config: SocialConfig) => void;
    onUseCustomToolsChange: (use: boolean) => void;
    onUseCustomMcpChange: (use: boolean) => void;
}

export function SocialTab({
    socialConfig,
    models,
    tools,
    mcpServers,
    useCustomTools,
    useCustomMcp,
    onConfigChange,
    onUseCustomToolsChange,
    onUseCustomMcpChange,
}: SocialTabProps): React.ReactElement {
    const { t } = useI18n();
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black">{t('settings.categories.social')}</h2>
            </div>

            <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-black border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.social.generalTitle')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.social.generalDesc')}</p>
                    </div>
                </div>

                <div className="space-y-4">
                    <div className="space-y-2">
                        <label className="text-sm font-bold uppercase text-neutral-800">
                            {t('settings.social.socialModelLabel')}
                        </label>
                        <BrutalSelect
                            value={socialConfig.model || ''}
                            onChange={(val) => onConfigChange({ ...socialConfig, model: val })}
                            options={[
                                { value: '', label: t('settings.social.useDefaultSystemModel') },
                                ...models.map((model) => ({ value: model, label: model }))
                            ]}
                            placeholder={t('settings.social.selectModelPlaceholder')}
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-bold uppercase text-neutral-800">
                            {t('settings.social.globalAllowedUsers')}
                        </label>
                        <input
                            type="text"
                            className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                            value={(socialConfig.allowed_users || []).join(', ')}
                            onChange={(e) => onConfigChange({ ...socialConfig, allowed_users: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                            placeholder={t('settings.social.globalAllowedUsersPlaceholder')}
                        />
                    </div>
                </div>
            </div>

            {/* Agent Capabilities Card */}
            <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.social.capabilitiesTitle')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.social.capabilitiesDesc')}</p>
                    </div>
                </div>

                <div className="space-y-6">
                    {/* Memory Toggle */}
                    <BrutalToggle
                        checked={socialConfig.memory_enabled !== false}
                        onChange={(checked) => onConfigChange({ ...socialConfig, memory_enabled: checked })}
                        label={t('settings.social.enableMemoryTools')}
                    />

                    {/* Tools Section */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-bold uppercase text-neutral-800">{t('settings.social.toolsLabel')}</label>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => {
                                        onUseCustomToolsChange(false);
                                        onConfigChange({ ...socialConfig, tools: null });
                                    }}
                                    className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${!useCustomTools ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                >
                                    {t('settings.social.toolsAll')}
                                </button>
                                <button
                                    onClick={() => {
                                        onUseCustomToolsChange(true);
                                        onConfigChange({ ...socialConfig, tools: socialConfig.tools || [] });
                                    }}
                                    className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${useCustomTools ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                >
                                    {t('settings.social.toolsCustom')}
                                </button>
                            </div>
                        </div>
                        {useCustomTools && (
                            <BrutalMultiSelect
                                variant="list"
                                value={socialConfig.tools || []}
                                onChange={(newVal) => onConfigChange({ ...socialConfig, tools: newVal })}
                                options={tools.map((t) => ({ value: t, label: t }))}
                                emptyMessage={t('settings.social.toolsEmpty')}
                                dropdownClassName="max-h-48"
                            />
                        )}
                    </div>

                    {/* MCP Section */}
                    {mcpServers && Object.keys(mcpServers.urls).length + Object.keys(mcpServers.stdio).length > 0 && (
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <label className="text-sm font-bold uppercase text-neutral-800">{t('settings.social.mcpServersLabel')}</label>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => {
                                            onUseCustomMcpChange(false);
                                            onConfigChange({ ...socialConfig, mcp_enabled: null });
                                        }}
                                        className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${!useCustomMcp ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                    >
                                        {t('settings.social.mcpSystemDefault')}
                                    </button>
                                    <button
                                        onClick={() => {
                                            onUseCustomMcpChange(true);
                                            onConfigChange({
                                                ...socialConfig,
                                                mcp_enabled: socialConfig.mcp_enabled || { ...mcpServers.enabled }
                                            });
                                        }}
                                        className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${useCustomMcp ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                    >
                                        {t('settings.social.mcpCustom')}
                                    </button>
                                </div>
                            </div>
                            {useCustomMcp && (
                                <div className="space-y-2 border-2 border-brutal-black p-3 bg-neutral-50">
                                    {[...Object.keys(mcpServers.urls), ...Object.keys(mcpServers.stdio)].map(name => (
                                        <BrutalToggle
                                            key={name}
                                            checked={socialConfig.mcp_enabled?.[name] ?? mcpServers.enabled[name] ?? true}
                                            onChange={(checked) => onConfigChange({
                                                ...socialConfig,
                                                mcp_enabled: { ...(socialConfig.mcp_enabled || {}), [name]: checked }
                                            })}
                                            label={name}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Platform-specific cards */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {Object.entries(socialConfig).map(([key, value]) => {
                    if (key === 'allowed_users' || key === 'model' || key === 'memory_enabled' || key === 'tools' || key === 'mcp_enabled') return null;
                    if (typeof value !== 'object' || value === null) return null;

                    const platformConfig = value as any;
                    const isEnabled = !!platformConfig.enabled;

                    return (
                        <div key={key} className="bg-white border-4 border-brutal-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] flex flex-col">
                            <div className="p-4 bg-neutral-50 flex justify-between items-center border-b-4 border-brutal-black">
                                <span className="font-black uppercase text-xl tracking-wide">{key}</span>
                                <div className={`w-4 h-4 rounded-full border-2 border-brutal-black ${isEnabled ? 'bg-brutal-green' : 'bg-transparent'}`}></div>
                            </div>

                            <div className="p-6 space-y-4">
                                <BrutalToggle
                                    checked={isEnabled}
                                    onChange={(checked) => onConfigChange({
                                        ...socialConfig,
                                        [key]: { ...platformConfig, enabled: checked }
                                    })}
                                    label={t('settings.social.enableToggle')}
                                    className="mb-4"
                                />

                                {Object.entries(platformConfig).map(([fieldKey, fieldVal]) => {
                                    if (fieldKey === 'enabled' || fieldKey === 'allowed_users') return null;

                                    const isSecret = fieldKey.includes('token') || fieldKey.includes('secret') || fieldKey.includes('key');

                                    return (
                                        <div key={fieldKey} className="space-y-1">
                                            <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">
                                                {fieldKey.replace(/_/g, ' ')}
                                            </label>
                                            <input
                                                type={isSecret ? "password" : "text"}
                                                value={fieldVal as string}
                                                onChange={(e) => onConfigChange({
                                                    ...socialConfig,
                                                    [key]: { ...platformConfig, [fieldKey]: e.target.value }
                                                })}
                                                className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                                            />
                                        </div>
                                    );
                                })}

                                <div className="space-y-1 pt-2 border-t-2 border-dashed border-neutral-300">
                                    <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">
                                        {t('settings.social.allowedUsersSpecific', { platform: key })}
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
                                        placeholder={t('settings.social.allowedUsersPlaceholder')}
                                        className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                                    />
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
