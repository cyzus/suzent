import React, { useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import { ApiField, ApiProvider, CustomProviderPayload, fetchChatGPTStatus, logoutChatGPT, startChatGPTLogin, syncCapabilities, UserConfig } from '../../lib/api';
import type { ChatGPTLoginResponse, ChatGPTStatusResponse } from '../../types/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalButton } from '../BrutalButton';
import { SettingsHeader } from './SettingsHeader';

// Brand colors keyed by provider id (hex without #). Kept in the frontend only.
const PROVIDER_COLORS: Record<string, string> = {
    openai:        '000000',
    chatgpt:       '74AA9C',
    anthropic:     'D97757',
    gemini:        '4285F4',
    xai:           '000000',
    dashscope:     'FF6A00',
    deepseek:      '4D6BFE',
    minimax:       '1F1E33',
    moonshot:      '1C1C1E',
    zhipuai:       '2B60D6',
    openrouter:    '6467F2',
    litellm_proxy: '7C3AED',
    ollama:        '000000',
    perplexity:    '20808D',
    together:      'FF5733',
    fireworks:     '9B59B6',
    sambanova:     'E34A34',
    bedrock:       'FF9900',
    xiaomi_mimo:   'FF6900',
};

const API_TYPES = ['openai', 'anthropic', 'google', 'xai', 'openrouter', 'ollama', 'litellm_proxy', 'bedrock'] as const;

type ProviderTab = 'credentials' | 'models';

interface ProvidersTabProps {
    providers: ApiProvider[];
    apiKeys: Record<string, string>;
    userConfigs: Record<string, UserConfig>;
    showKey: Record<string, boolean>;
    activeTabs: Record<string, ProviderTab>;
    verifying: Record<string, boolean>;
    onKeyChange: (key: string, val: string) => void;
    onToggleShowKey: (key: string) => void;
    onTabChange: (providerId: string, tab: ProviderTab) => void;
    onConfigChange: (providerId: string, config: UserConfig) => void;
    onAddCustomModel: (providerId: string, modelId: string) => void;
    onVerify: (provider: ApiProvider) => void;
    onAddProvider: (payload: CustomProviderPayload) => Promise<void>;
    onDeleteProvider: (providerId: string) => Promise<void>;
    onChatGPTAuthChanged?: () => Promise<void> | void;
}

// ─── KeyStatusBadge ──────────────────────────────────────────────────────────

function KeyStatusBadge({ fields }: { fields: ApiField[] }) {
    const secretFields = fields.filter(f => f.type === 'secret');
    if (secretFields.length === 0) return null;
    const hasKey = secretFields.some(f => f.isSet);

    return (
        <span className={`text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 border-2 ${hasKey ? 'border-brutal-black bg-brutal-black text-white dark:bg-white dark:text-brutal-black' : 'border-brutal-black text-brutal-black dark:border-white dark:text-white bg-transparent'}`}>
            {hasKey ? 'key set' : 'no key'}
        </span>
    );
}

// ─── ProviderIcon ────────────────────────────────────────────────────────────

function ProviderIcon({ provider }: { provider: ApiProvider }) {
    const [imgFailed, setImgFailed] = useState(false);
    const color = PROVIDER_COLORS[provider.id] ?? (provider.user_defined ? '6B7280' : 'e5e5e5');
    const initials = provider.label.slice(0, 2).toUpperCase();
    return (
        <div
            className="w-9 h-9 border-2 border-brutal-black flex items-center justify-center flex-shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
            style={{ backgroundColor: `#${color}` }}
        >
            {provider.logo_url && !imgFailed ? (
                <img
                    src={provider.logo_url.includes('simpleicons.org') ? `${provider.logo_url}/ffffff` : provider.logo_url}
                    alt={provider.label}
                    className="w-5 h-5 object-contain"
                    onError={() => setImgFailed(true)}
                />
            ) : (
                <span className="text-[10px] font-black text-white select-none">{initials}</span>
            )}
        </div>
    );
}

// ─── AddProviderForm ─────────────────────────────────────────────────────────

interface AddProviderFormProps {
    onSave: (payload: CustomProviderPayload) => Promise<void>;
    onCancel: () => void;
}

function AddProviderForm({ onSave, onCancel }: AddProviderFormProps) {
    const { t } = useI18n();
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({
        id: '',
        label: '',
        api_type: 'openai' as string,
        base_url: '',
        key_env: '',
        key_label: 'API Key',
        key_placeholder: '',
    });
    const [error, setError] = useState('');

    const set = (key: string, val: string) => setForm(f => ({ ...f, [key]: val }));

    const handleSave = async () => {
        if (!form.id.trim() || !form.label.trim()) {
            setError(t('settings.providers.addForm.requiredFields'));
            return;
        }
        setSaving(true);
        setError('');
        const payload: CustomProviderPayload = {
            id: form.id.trim(),
            label: form.label.trim(),
            api_type: form.api_type,
            ...(form.base_url.trim() && { base_url: form.base_url.trim() }),
            ...(form.key_env.trim() && {
                env_keys: [form.key_env.trim()],
                fields: [{
                    key: form.key_env.trim(),
                    label: form.key_label.trim() || 'API Key',
                    placeholder: form.key_placeholder.trim() || '...',
                    type: 'secret',
                }],
            }),
            default_models: [],
        };
        try {
            await onSave(payload);
        } catch (e: any) {
            setError(e.message || 'Failed to save provider');
            setSaving(false);
        }
    };

    return (
        <div className="bg-white dark:bg-zinc-800 border-3 border-brutal-black shadow-brutal-xl p-6 space-y-4">
            <h3 className="font-black uppercase text-lg tracking-wide dark:text-white">{t('settings.providers.addForm.title')}</h3>

            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                    <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{t('settings.providers.addForm.id')} *</label>
                    <input
                        type="text"
                        value={form.id}
                        onChange={e => set('id', e.target.value.replace(/\s/g, '_').toLowerCase())}
                        placeholder="my_provider"
                        className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                    />
                </div>
                <div className="space-y-1">
                    <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{t('settings.providers.addForm.label')} *</label>
                    <input
                        type="text"
                        value={form.label}
                        onChange={e => set('label', e.target.value)}
                        placeholder="My Provider"
                        className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                    />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                    <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{t('settings.providers.addForm.apiType')}</label>
                    <select
                        value={form.api_type}
                        onChange={e => set('api_type', e.target.value)}
                        className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                    >
                        {API_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                </div>
                <div className="space-y-1">
                    <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{t('settings.providers.addForm.baseUrl')}</label>
                    <input
                        type="text"
                        value={form.base_url}
                        onChange={e => set('base_url', e.target.value)}
                        placeholder="https://api.example.com/v1"
                        className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                    />
                </div>
            </div>

            <div className="border-t-2 border-neutral-200 dark:border-zinc-700 pt-4 space-y-3">
                <p className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{t('settings.providers.addForm.apiKeySection')}</p>
                <div className="grid grid-cols-3 gap-3">
                    <div className="space-y-1">
                        <label className="text-[10px] font-bold uppercase text-neutral-400 tracking-wider">{t('settings.providers.addForm.envVar')}</label>
                        <input
                            type="text"
                            value={form.key_env}
                            onChange={e => set('key_env', e.target.value.toUpperCase().replace(/\s/g, '_'))}
                            placeholder="MY_PROVIDER_API_KEY"
                            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                        />
                    </div>
                    <div className="space-y-1">
                        <label className="text-[10px] font-bold uppercase text-neutral-400 tracking-wider">{t('settings.providers.addForm.fieldLabel')}</label>
                        <input
                            type="text"
                            value={form.key_label}
                            onChange={e => set('key_label', e.target.value)}
                            placeholder="API Key"
                            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                        />
                    </div>
                    <div className="space-y-1">
                        <label className="text-[10px] font-bold uppercase text-neutral-400 tracking-wider">{t('settings.providers.addForm.placeholder')}</label>
                        <input
                            type="text"
                            value={form.key_placeholder}
                            onChange={e => set('key_placeholder', e.target.value)}
                            placeholder="sk-..."
                            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white"
                        />
                    </div>
                </div>
            </div>

            {error && <p className="text-red-600 text-xs font-bold">{error}</p>}

            <div className="flex gap-3 justify-end pt-2">
                <button onClick={onCancel} className="px-4 py-2 text-xs font-black uppercase border-2 border-brutal-black hover:bg-neutral-100 dark:hover:bg-zinc-700 dark:text-white">
                    {t('common.cancel')}
                </button>
                <BrutalButton
                    variant="dark"
                    onClick={handleSave}
                    disabled={saving}
                    className="text-xs px-4 py-2 font-black uppercase"
                >
                    {saving ? t('common.saving') : t('settings.providers.addForm.save')}
                </BrutalButton>
            </div>
        </div>
    );
}

function ChatGPTProviderCard({
    provider,
    config,
    onConfigChange,
    onAuthChanged,
    onVerify,
    verifying,
}: {
    provider: ApiProvider;
    config: UserConfig;
    onConfigChange: (providerId: string, config: UserConfig) => void;
    onAuthChanged?: () => Promise<void> | void;
    onVerify: (provider: ApiProvider) => void;
    verifying: boolean;
}): React.ReactElement {
    const { t } = useI18n();
    const [status, setStatus] = useState<ChatGPTStatusResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [pendingLogin, setPendingLogin] = useState<ChatGPTLoginResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    const refresh = async () => {
        setLoading(true);
        try {
            const result = await fetchChatGPTStatus();
            setStatus(result);
            setError(result?.error ?? null);
            if (result?.connected && config.enabled_models.length === 0) {
                const defaults = provider.default_models.map(m => m.id);
                if (defaults.length > 0) {
                    onConfigChange(provider.id, { ...config, enabled_models: defaults });
                }
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { void refresh(); }, [provider.id]); // eslint-disable-line react-hooks/exhaustive-deps

    // Poll /chatgpt/status until connected, while device code is displayed
    useEffect(() => {
        if (!pendingLogin) return;
        const timer = setInterval(async () => {
            const result = await fetchChatGPTStatus();
            if (result?.connected) {
                setPendingLogin(null);
                setStatus(result);
                if (config.enabled_models.length === 0) {
                    const defaults = provider.default_models.map(m => m.id);
                    if (defaults.length > 0) onConfigChange(provider.id, { ...config, enabled_models: defaults });
                }
                await onAuthChanged?.();
            }
        }, 3000);
        return () => clearInterval(timer);
    }, [pendingLogin]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleSignIn = async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await startChatGPTLogin();
            if (result.success) {
                setPendingLogin(result);
            } else {
                setError(result.error ?? 'Failed to start login');
            }
        } finally {
            setLoading(false);
        }
    };

    const handleDisconnect = async () => {
        setLoading(true);
        setError(null);
        setPendingLogin(null);
        try {
            await logoutChatGPT();
            await refresh();
            await onAuthChanged?.();
        } finally {
            setLoading(false);
        }
    };

    const statusKey = status?.status ?? 'not_logged_in';
    const connected = status?.connected === true;
    const allModels = provider.default_models || [];

    return (
        <div className="bg-white dark:bg-zinc-800 dark:text-white border-3 border-brutal-black shadow-brutal-xl flex flex-col h-full">
            <div className="p-4 bg-neutral-50 dark:bg-zinc-900 flex justify-between items-center border-b-3 border-brutal-black gap-3">
                <div className="flex items-center gap-3 min-w-0">
                    <ProviderIcon provider={provider} />
                    <div className="flex flex-col min-w-0">
                        <span className={`font-black uppercase tracking-wide leading-tight dark:text-white ${provider.label.length > 14 ? 'text-sm' : provider.label.length > 10 ? 'text-base' : 'text-xl'}`}>{provider.label}</span>
                        <span className="text-[9px] font-bold uppercase tracking-wider text-neutral-400">{t('settings.providers.chatgpt.subtitle')}</span>
                    </div>
                </div>
                <span className={`text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 border-2 border-brutal-black ${connected ? 'bg-brutal-green text-brutal-black' : 'bg-white dark:bg-zinc-800 dark:text-white'}`}>
                    {t(`settings.providers.chatgpt.status.${statusKey}` as any)}
                </span>
            </div>

            <div className="p-6 flex flex-col gap-4 flex-1">
                {pendingLogin && (
                    <div className="space-y-3 p-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900">
                        <p className="text-xs font-bold text-neutral-700 dark:text-neutral-300">
                            {t('settings.providers.chatgpt.awaitingAuth')}
                        </p>
                        <a
                            href={pendingLogin.verify_url}
                            target="_blank"
                            rel="noreferrer"
                            className="block text-xs font-mono underline text-blue-600 dark:text-blue-400 break-all"
                        >
                            {pendingLogin.verify_url}
                        </a>
                        <div className="flex flex-col gap-2">
                            <span className="inline-flex w-fit max-w-full font-mono text-xl sm:text-2xl font-black tracking-[0.22em] border-4 border-brutal-black px-3 py-2 dark:text-white select-all whitespace-nowrap overflow-x-auto">
                                {pendingLogin.user_code}
                            </span>
                            <span className="text-[10px] text-neutral-400 uppercase font-bold animate-pulse">
                                {t('settings.providers.chatgpt.waiting')}
                            </span>
                        </div>
                    </div>
                )}

                <div className="space-y-2">
                    {error && (
                        <p className="text-[11px] font-bold text-red-600">{error}</p>
                    )}
                </div>

                <div className="flex flex-wrap gap-2">
                    {!connected && !pendingLogin && (
                        <button
                            onClick={handleSignIn}
                            disabled={loading}
                            className="px-3 py-2 text-xs font-black uppercase bg-brutal-black text-white border-2 border-brutal-black hover:bg-zinc-800 disabled:opacity-50"
                        >
                            {t('settings.providers.chatgpt.signIn')}
                        </button>
                    )}
                    {pendingLogin && (
                        <button
                            onClick={() => setPendingLogin(null)}
                            disabled={loading}
                            className="px-3 py-2 text-xs font-black uppercase border-2 border-brutal-black text-neutral-500 hover:bg-neutral-100 dark:hover:bg-zinc-700 disabled:opacity-50"
                        >
                            Cancel
                        </button>
                    )}
                    {connected && (
                        <button
                            onClick={handleDisconnect}
                            disabled={loading}
                            className="px-3 py-2 text-xs font-black uppercase border-2 border-brutal-black text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-50"
                        >
                            {t('settings.providers.chatgpt.disconnect')}
                        </button>
                    )}
                    <button
                        onClick={refresh}
                        disabled={loading}
                        className="px-3 py-2 text-xs font-black uppercase border-2 border-brutal-black text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700 disabled:opacity-50"
                    >
                        {loading ? t('common.loading') : t('common.refresh')}
                    </button>
                </div>

                <div className="pt-2 border-t-2 border-neutral-200 dark:border-zinc-700 space-y-2">
                    <div className="flex items-center justify-between">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                            {t('settings.providers.modelsTab')}
                        </p>
                        <BrutalButton
                            variant="primary"
                            onClick={() => onVerify(provider)}
                            disabled={verifying || !connected}
                            className="text-xs px-3 py-1 font-black uppercase"
                        >
                            {verifying ? t('settings.providers.fetching') : t('settings.providers.fetch')}
                        </BrutalButton>
                    </div>
                    <BrutalMultiSelect
                        variant="list"
                        value={config.enabled_models}
                        onChange={(newVal) => onConfigChange(provider.id, { ...config, enabled_models: newVal })}
                        options={allModels.map(m => ({ value: m.id, label: m.name || m.id }))}
                        emptyMessage={t('settings.providers.noModelsFound')}
                        dropdownClassName="max-h-48"
                    />
                </div>
            </div>
        </div>
    );
}

// ─── ProvidersTab ─────────────────────────────────────────────────────────────

export function ProvidersTab({
    providers,
    apiKeys,
    userConfigs,
    showKey,
    activeTabs,
    verifying,
    onKeyChange,
    onToggleShowKey,
    onTabChange,
    onConfigChange,
    onAddCustomModel,
    onVerify,
    onAddProvider,
    onDeleteProvider,
    onChatGPTAuthChanged,
}: ProvidersTabProps): React.ReactElement {
    const { t } = useI18n();
    const [showAddForm, setShowAddForm] = useState(false);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [syncing, setSyncing] = useState(false);
    const [syncResult, setSyncResult] = useState<string | null>(null);
    // Tracks which secret field keys are currently in edit mode (user clicked "Change")
    const [editingFields, setEditingFields] = useState<Set<string>>(new Set());

    const startEditing = (fieldKey: string) => {
        setEditingFields(prev => new Set(prev).add(fieldKey));
        onKeyChange(fieldKey, '');
    };

    const cancelEditing = (field: ApiField) => {
        setEditingFields(prev => { const s = new Set(prev); s.delete(field.key); return s; });
        onKeyChange(field.key, field.value);
    };

    const handleSaveProvider = async (payload: CustomProviderPayload) => {
        await onAddProvider(payload);
        setShowAddForm(false);
    };

    const handleDelete = async (providerId: string) => {
        setDeletingId(providerId);
        try {
            await onDeleteProvider(providerId);
        } finally {
            setDeletingId(null);
        }
    };

    const handleSync = async () => {
        setSyncing(true);
        setSyncResult(null);
        try {
            const result = await syncCapabilities();
            if (result.success) {
                setSyncResult(t('settings.providers.syncDone', { providers: String(result.providers ?? 0), models: String(result.models ?? 0) }));
            } else {
                setSyncResult(result.error || t('settings.providers.syncFailed'));
            }
        } finally {
            setSyncing(false);
            setTimeout(() => setSyncResult(null), 5000);
        }
    };

    return (
        <div className="space-y-6">
            <SettingsHeader
                title={t('settings.providers.title')}
                subtitle={t('settings.providers.subtitle')}
                actions={
                    <>
                        {syncResult && (
                            <span className="text-[10px] font-bold text-neutral-300 max-w-[200px] truncate">{syncResult}</span>
                        )}
                        <button
                            onClick={handleSync}
                            disabled={syncing}
                            title={t('settings.providers.syncTooltip')}
                            className="px-3 py-2 text-xs font-black uppercase border-2 border-white text-white hover:bg-white/10 disabled:opacity-40 active:translate-y-px"
                        >
                            {syncing ? t('settings.providers.syncing') : t('settings.providers.sync')}
                        </button>
                        <button
                            onClick={() => setShowAddForm(v => !v)}
                            className="px-3 py-2 text-xs font-black uppercase bg-white text-brutal-black border-2 border-white hover:bg-neutral-200 active:translate-y-px"
                        >
                            {showAddForm ? '✕' : t('settings.providers.addProvider')}
                        </button>
                    </>
                }
            />

            {showAddForm && (
                <AddProviderForm
                    onSave={handleSaveProvider}
                    onCancel={() => setShowAddForm(false)}
                />
            )}

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {providers.map((provider) => {
                    const activeTab = activeTabs[provider.id] || 'credentials';
                    const conf = userConfigs[provider.id] || { enabled_models: [], custom_models: [] };
                    const isEnabled = conf.enabled_models.length > 0;

                    if (provider.id === 'chatgpt') {
                        return (
                            <ChatGPTProviderCard
                                key={provider.id}
                                provider={provider}
                                config={conf}
                                onConfigChange={onConfigChange}
                                onAuthChanged={onChatGPTAuthChanged}
                                onVerify={onVerify}
                                verifying={!!verifying[provider.id]}
                            />
                        );
                    }

                    const allModels = [...(provider.default_models || [])];

                    for (const model of provider.models || []) {
                        if (!allModels.find(x => x.id === model.id)) {
                            allModels.push(model);
                        }
                    }

                    for (const modelId of conf.custom_models) {
                        if (!allModels.find(x => x.id === modelId)) {
                            allModels.push({ id: modelId, name: modelId });
                        }
                    }

                    for (const modelId of conf.enabled_models) {
                        if (!allModels.find(x => x.id === modelId)) {
                            allModels.push({ id: modelId, name: modelId });
                        }
                    }

                    return (
                        <div key={provider.id} className="bg-white dark:bg-zinc-800 dark:text-white border-3 border-brutal-black shadow-brutal-xl flex flex-col h-full">
                            {/* Provider Header */}
                            <div className="p-4 bg-neutral-50 dark:bg-zinc-900 flex justify-between items-center border-b-3 border-brutal-black gap-3">
                                <div className="flex items-center gap-3 min-w-0">
                                    <ProviderIcon provider={provider} />
                                    <div className="flex flex-col min-w-0">
                                        <span className={`font-black uppercase tracking-wide leading-tight dark:text-white ${provider.label.length > 14 ? 'text-sm' : provider.label.length > 10 ? 'text-base' : 'text-xl'}`}>{provider.label}</span>
                                        {provider.user_defined && (
                                            <span className="text-[9px] font-bold uppercase tracking-wider text-neutral-400">custom</span>
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 flex-shrink-0">
                                    <KeyStatusBadge fields={provider.fields} />
                                    {provider.user_defined && (
                                        <button
                                            onClick={() => handleDelete(provider.id)}
                                            disabled={deletingId === provider.id}
                                            className="text-[10px] font-black uppercase px-2 py-1 border-2 border-brutal-black text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700 disabled:opacity-40"
                                            title={t('settings.providers.deleteProvider')}
                                        >
                                            {deletingId === provider.id ? '…' : '✕'}
                                        </button>
                                    )}
                                    <div className={`w-4 h-4 rounded-full border-2 border-brutal-black ${isEnabled ? 'bg-brutal-green' : 'bg-transparent'}`}></div>
                                </div>
                            </div>

                            {/* Tabs */}
                            <div className="flex bg-brutal-black border-b-3 border-brutal-black">
                                <button
                                    onClick={() => onTabChange(provider.id, 'credentials')}
                                    className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors border-r-3 border-brutal-black ${activeTab === 'credentials' ? 'bg-brutal-black text-white dark:bg-zinc-900' : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'}`}
                                >
                                    {t('settings.providers.apiKeysTab')}
                                </button>
                                <button
                                    onClick={() => onTabChange(provider.id, 'models')}
                                    className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors ${activeTab === 'models' ? 'bg-brutal-black text-white dark:bg-zinc-900' : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'}`}
                                >
                                    {t('settings.providers.modelsTab')}
                                </button>
                            </div>

                            <div className="p-6 flex flex-col gap-4 flex-1">
                                {activeTab === 'credentials' && (
                                    <div className="space-y-4">
                                        {provider.fields.map(field => {
                                            const val = apiKeys[field.key] ?? '';
                                            const isConfigured = field.isSet && !editingFields.has(field.key);
                                            const isEnvKey = field.source === 'env'; // display-only hint

                                            return (
                                                <div key={field.key} className="space-y-1">
                                                    <div className="flex items-center justify-between">
                                                        <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{field.label}</label>
                                                        {isConfigured && (
                                                            <span className="text-[9px] font-bold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                                                                {isEnvKey ? 'env' : 'saved'}
                                                            </span>
                                                        )}
                                                    </div>

                                                    {isConfigured ? (
                                                        /* Locked/display state */
                                                        <div className="flex gap-0 min-w-0">
                                                            <div className="flex-1 min-w-0 flex items-center bg-neutral-100 dark:bg-zinc-800 border-2 border-brutal-black px-3 py-2">
                                                                <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400 truncate">{val || '••••••••'}</span>
                                                            </div>
                                                            <button
                                                                onClick={() => startEditing(field.key)}
                                                                className="shrink-0 px-3 text-[10px] font-black uppercase border-2 border-l-0 border-brutal-black text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700 bg-white dark:bg-zinc-900 whitespace-nowrap"
                                                            >
                                                                {t('settings.providers.changeKey')}
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        /* Edit state */
                                                        (() => {
                                                            const showToggle = field.type === 'secret' && val.length > 0;
                                                            const showCancel = field.isSet && editingFields.has(field.key);
                                                            const hasRight = showToggle || showCancel;
                                                            return (
                                                                <div className="flex gap-0">
                                                                    <div className="relative flex-1">
                                                                        <input
                                                                            type={field.type === 'secret' ? (showKey[field.key] ? 'text' : 'password') : 'text'}
                                                                            value={val}
                                                                            onChange={(e) => onKeyChange(field.key, e.target.value)}
                                                                            placeholder={field.placeholder}
                                                                            autoFocus={editingFields.has(field.key)}
                                                                            className={`w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 transition-all dark:text-white ${hasRight ? 'border-r-0' : ''}`}
                                                                        />
                                                                    </div>
                                                                    {showToggle && (
                                                                        <button
                                                                            onClick={() => onToggleShowKey(field.key)}
                                                                            className={`w-9 flex items-center justify-center bg-white dark:bg-zinc-900 border-2 border-brutal-black hover:bg-neutral-100 dark:hover:bg-zinc-800 font-mono text-xs dark:text-white select-none ${showCancel ? 'border-r-0' : ''}`}
                                                                            title={showKey[field.key] ? t('settings.providers.hideKey') : t('settings.providers.showKey')}
                                                                        >
                                                                            {showKey[field.key] ? '○' : '●'}
                                                                        </button>
                                                                    )}
                                                                    {showCancel && (
                                                                        <button
                                                                            onClick={() => cancelEditing(field)}
                                                                            className="px-3 text-[10px] font-black uppercase border-2 border-brutal-black text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-zinc-700 bg-white dark:bg-zinc-900 whitespace-nowrap"
                                                                        >
                                                                            {t('common.cancel')}
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            );
                                                        })()
                                                    )}
                                                </div>
                                            );
                                        })}
                                        {provider.fields.length === 0 && (
                                            <p className="text-xs text-neutral-400 italic">{t('settings.providers.noCredentials')}</p>
                                        )}
                                    </div>
                                )}

                                {activeTab === 'models' && (
                                    <div className="flex flex-col h-full pt-2">
                                        {/* Input Row with Fetch Button */}
                                        <div className="flex gap-2 mb-4">
                                            <div className="flex flex-1 gap-0">
                                                <input
                                                    type="text"
                                                    placeholder={t('settings.providers.addModelIdPlaceholder')}
                                                    className="flex-1 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter') {
                                                            onAddCustomModel(provider.id, e.currentTarget.value);
                                                            e.currentTarget.value = '';
                                                        }
                                                    }}
                                                />
                                                <button className="bg-brutal-black text-white w-10 font-bold border-2 border-brutal-black hover:bg-neutral-800 flex items-center justify-center text-lg">+</button>
                                            </div>
                                            <BrutalButton
                                                variant="primary"
                                                onClick={() => onVerify(provider)}
                                                disabled={verifying[provider.id]}
                                                className="text-xs px-4 py-2 font-black uppercase shrink-0"
                                            >
                                                {verifying[provider.id] ? t('settings.providers.fetching') : t('settings.providers.fetch')}
                                            </BrutalButton>
                                        </div>

                                        {/* Models List (Scrollable) */}
                                        <BrutalMultiSelect
                                            variant="list"
                                            value={conf.enabled_models}
                                            onChange={(newVal) => onConfigChange(provider.id, { ...conf, enabled_models: newVal })}
                                            options={allModels.map(m => ({ value: m.id, label: m.name || m.id }))}
                                            emptyMessage={t('settings.providers.noModelsFound')}
                                            emptyAction={
                                                <button onClick={() => onVerify(provider)} className="underline hover:text-black">{t('settings.providers.fetchModels')}</button>
                                            }
                                            dropdownClassName="max-h-80"
                                        />

                                        {/* Footer */}
                                        <div className="flex justify-between items-center px-1 mt-2">
                                            <span className="text-[10px] text-neutral-500 font-bold uppercase tracking-wider">{t('settings.providers.modelsAvailable', { count: String(allModels.length) })}</span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
