import React from 'react';

import { useI18n } from '../../i18n';
import { ApiProvider, UserConfig } from '../../lib/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';

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
}

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
}: ProvidersTabProps): React.ReactElement {
    const { t } = useI18n();

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black">{t('settings.providers.title')}</h2>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {providers.map((provider) => {
                    const activeTab = activeTabs[provider.id] || 'credentials';
                    const conf = userConfigs[provider.id] || { enabled_models: [], custom_models: [] };
                    const isEnabled = conf.enabled_models.length > 0;

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
                        <div key={provider.id} className="bg-white border-4 border-brutal-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] flex flex-col h-full">
                            {/* Provider Header */}
                            <div className="p-4 bg-neutral-50 flex justify-between items-center border-b-4 border-brutal-black">
                                <span className="font-black uppercase text-xl tracking-wide">{provider.label}</span>
                                <div className={`w-4 h-4 rounded-full border-2 border-brutal-black ${isEnabled ? 'bg-brutal-green' : 'bg-transparent'}`}></div>
                            </div>

                            {/* Tabs */}
                            <div className="flex bg-brutal-black border-b-4 border-brutal-black">
                                <button
                                    onClick={() => onTabChange(provider.id, 'credentials')}
                                    className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors ${activeTab === 'credentials' ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                >
                                    {t('settings.providers.apiKeysTab')}
                                </button>
                                <button
                                    onClick={() => onTabChange(provider.id, 'models')}
                                    className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors ${activeTab === 'models' ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                >
                                    {t('settings.providers.modelsTab')}
                                </button>
                            </div>

                            <div className="p-6 flex flex-col gap-4 flex-1">
                                {activeTab === 'credentials' && (
                                    <div className="space-y-4">
                                        {provider.fields.map(field => {
                                            const val = apiKeys[field.key] || '';
                                            const isMasked = val === '********' || (val.includes('...') && val.includes('(env)'));
                                            const inputType = field.type === 'secret' ? (showKey[field.key] ? "text" : "password") : "text";
                                            return (
                                                <div key={field.key} className="space-y-1">
                                                    <label className="text-[10px] font-bold uppercase text-neutral-500 tracking-wider">{field.label}</label>
                                                    <div className="flex gap-0">
                                                        <div className="relative flex-1">
                                                            <input
                                                                type={inputType}
                                                                value={val}
                                                                onChange={(e) => onKeyChange(field.key, e.target.value)}
                                                                placeholder={field.placeholder}
                                                                className={`w-full bg-white border-2 border-brutal-black border-r-0 px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 transition-all ${isMasked ? 'text-neutral-500 italic' : ''}`}
                                                            />
                                                        </div>
                                                        {field.type === 'secret' && (
                                                            <button
                                                                onClick={() => onToggleShowKey(field.key)}
                                                                className="w-10 flex items-center justify-center bg-white border-2 border-brutal-black hover:bg-neutral-100 font-bold text-[10px]"
                                                            >
                                                                {showKey[field.key] ? 'H' : 'S'}
                                                            </button>
                                                        )}
                                                        {field.type !== 'secret' && (
                                                            <div className="w-10 border-2 border-brutal-black border-l-0 bg-neutral-100"></div>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
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
                                                    className="flex-1 bg-white border-2 border-brutal-black border-r-0 px-3 py-2 font-mono text-xs focus:outline-none"
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter') {
                                                            onAddCustomModel(provider.id, e.currentTarget.value);
                                                            e.currentTarget.value = '';
                                                        }
                                                    }}
                                                />
                                                <button className="bg-brutal-black text-white w-10 font-bold border-2 border-brutal-black hover:bg-neutral-800 flex items-center justify-center text-lg">+</button>
                                            </div>
                                            <button
                                                onClick={() => onVerify(provider)}
                                                disabled={verifying[provider.id]}
                                                className="text-xs bg-brutal-blue text-white px-4 py-2 font-black uppercase border-2 border-brutal-black hover:translate-y-0.5 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none transition-all disabled:opacity-50 shrink-0"
                                            >
                                                {verifying[provider.id] ? t('settings.providers.fetching') : t('settings.providers.fetch')}
                                            </button>
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
