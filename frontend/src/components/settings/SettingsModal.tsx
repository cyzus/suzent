import React, { useEffect, useState } from 'react';

import { useChatStore } from '../../hooks/useChatStore';
import { ApiProvider, fetchApiKeys, saveApiKeys, UserConfig, verifyProvider } from '../../lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type ProviderTab = 'credentials' | 'models';

export function SettingsModal({ isOpen, onClose }: SettingsModalProps): React.ReactElement | null {
  const { refreshBackendConfig } = useChatStore();
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [userConfigs, setUserConfigs] = useState<Record<string, UserConfig>>({});
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [activeTabs, setActiveTabs] = useState<Record<string, ProviderTab>>({});
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    setLoading(true);
    fetchApiKeys().then(data => {
      if (!data?.providers) {
        setLoading(false);
        return;
      }

      setProviders(data.providers);

      const initialKeys: Record<string, string> = {};
      const initialConfigs: Record<string, UserConfig> = {};
      const initialTabs: Record<string, ProviderTab> = {};

      for (const provider of data.providers) {
        for (const field of provider.fields) {
          if (field.value) {
            initialKeys[field.key] = field.value;
          }
        }
        initialConfigs[provider.id] = provider.user_config || { enabled_models: [], custom_models: [] };
        initialTabs[provider.id] = 'credentials';
      }

      setApiKeys(initialKeys);
      setUserConfigs(initialConfigs);
      setActiveTabs(initialTabs);
      setLoading(false);
    });
  }, [isOpen]);

  function handleKeyChange(key: string, val: string): void {
    setApiKeys(prev => ({ ...prev, [key]: val }));
  }

  function toggleModel(providerId: string, modelId: string): void {
    setUserConfigs(prev => {
      const current = prev[providerId] || { enabled_models: [], custom_models: [] };
      const enabled = new Set(current.enabled_models);
      if (enabled.has(modelId)) {
        enabled.delete(modelId);
      } else {
        enabled.add(modelId);
      }
      return {
        ...prev,
        [providerId]: { ...current, enabled_models: Array.from(enabled) }
      };
    });
  }

  function addCustomModel(providerId: string, modelId: string): void {
    const trimmed = modelId.trim();
    if (!trimmed) return;

    setUserConfigs(prev => {
      const current = prev[providerId] || { enabled_models: [], custom_models: [] };
      if (current.custom_models.includes(trimmed)) return prev;

      return {
        ...prev,
        [providerId]: {
          ...current,
          custom_models: [...current.custom_models, trimmed],
          enabled_models: [...current.enabled_models, trimmed]
        }
      };
    });
  }

  async function handleVerify(provider: ApiProvider): Promise<void> {
    setVerifying(prev => ({ ...prev, [provider.id]: true }));

    const configForProvider: Record<string, string> = {};
    for (const field of provider.fields) {
      const val = apiKeys[field.key];
      if (val && val !== '********' && !val.includes('(env)')) {
        configForProvider[field.key] = val;
      }
    }

    const result = await verifyProvider(provider.id, configForProvider);

    if (result.success && result.models.length > 0) {
      setProviders(prev => prev.map(p =>
        p.id === provider.id ? { ...p, models: result.models } : p
      ));
    } else {
      alert("Verification failed or no models found.");
    }

    setVerifying(prev => ({ ...prev, [provider.id]: false }));
  }

  async function handleSave(): Promise<void> {
    setSaving(true);

    const keysToSave: Record<string, string> = {};
    for (const [key, value] of Object.entries(apiKeys)) {
      if (value === '********') continue;
      if (value.includes('...') && value.includes('(env)')) continue;
      keysToSave[key] = value;
    }

    const configBlob = JSON.stringify(userConfigs);
    await saveApiKeys({ ...keysToSave, "_PROVIDER_CONFIG_": configBlob });
    await refreshBackendConfig();

    setSaving(false);
    onClose();
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center animate-view-fade">
      <div className="absolute inset-0 bg-brutal-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full h-full md:w-[90%] md:h-[90%] bg-white border-4 border-brutal-black shadow-brutal-xl flex flex-col overflow-hidden">
        <div className="bg-brutal-yellow border-b-4 border-brutal-black p-6 flex justify-between items-center shadow-md z-10">
          <div>
            <h1 className="text-4xl font-brutal font-bold uppercase tracking-tighter text-brutal-black">
              Configuration
            </h1>
            <p className="font-mono text-sm font-bold text-neutral-600 uppercase mt-1">
              Manage Providers & Models
            </p>
          </div>
          <button onClick={onClose} className="w-12 h-12 bg-brutal-black text-white hover:bg-neutral-800 flex items-center justify-center transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-8 bg-neutral-100">
          <div className="max-w-5xl mx-auto">
            {loading ? (
              <div className="flex justify-center items-center h-64">
                <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-brutal-black"></div>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pb-8">
                {providers.map((provider) => {
                  const activeTab = activeTabs[provider.id];
                  const conf = userConfigs[provider.id] || { enabled_models: [], custom_models: [] };

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
                    <div key={provider.id} className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] flex flex-col transition-all duration-200">
                      <div className="flex border-b-4 border-brutal-black">
                        <button
                          onClick={() => setActiveTabs(p => ({ ...p, [provider.id]: 'credentials' }))}
                          className={`flex-1 p-3 font-bold uppercase text-sm transition-colors ${activeTab === 'credentials' ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                        >
                          Credentials
                        </button>
                        <button
                          onClick={() => setActiveTabs(p => ({ ...p, [provider.id]: 'models' }))}
                          className={`flex-1 p-3 font-bold uppercase text-sm transition-colors ${activeTab === 'models' ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                        >
                          Models
                        </button>
                      </div>

                      <div className="p-5 flex flex-col gap-4">
                        <div className="flex justify-between items-center mb-2">
                          <label className="text-xl font-bold uppercase text-brutal-black tracking-wide">{provider.label}</label>
                          {activeTab === 'models' && (
                            <button
                              onClick={() => handleVerify(provider)}
                              disabled={verifying[provider.id]}
                              className="text-[10px] bg-brutal-blue text-white px-2 py-1 font-bold uppercase border-2 border-brutal-black hover:translate-y-0.5 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none transition-all disabled:opacity-50"
                            >
                              {verifying[provider.id] ? '...' : 'Verify & Fetch'}
                            </button>
                          )}
                        </div>

                        {activeTab === 'credentials' && (
                          <div className="space-y-4">
                            {provider.fields.map(field => {
                              const val = apiKeys[field.key] || '';
                              const isMasked = val === '********' || (val.includes('...') && val.includes('(env)'));
                              const inputType = field.type === 'secret' ? (showKey[field.key] ? "text" : "password") : "text";
                              return (
                                <div key={field.key} className="space-y-1">
                                  <label className="text-xs font-bold uppercase text-neutral-600">{field.label}</label>
                                  <div className="flex gap-2">
                                    <div className="relative flex-1">
                                      <input
                                        type={inputType}
                                        value={val}
                                        onChange={(e) => handleKeyChange(field.key, e.target.value)}
                                        placeholder={field.placeholder}
                                        className={`w-full bg-neutral-50 border-2 border-brutal-black px-3 py-2 font-mono text-sm focus:outline-none focus:bg-white focus:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] transition-all ${isMasked ? 'text-neutral-500 italic' : ''}`}
                                      />
                                    </div>
                                    {field.type === 'secret' && (
                                      <button
                                        onClick={() => setShowKey(prev => ({ ...prev, [field.key]: !prev[field.key] }))}
                                        className="w-12 flex items-center justify-center bg-white border-2 border-brutal-black hover:bg-neutral-100 font-bold text-[10px] uppercase"
                                      >
                                        {showKey[field.key] ? 'HIDE' : 'SHOW'}
                                      </button>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {activeTab === 'models' && (
                          <div className="space-y-4">
                            <div className="flex gap-2">
                              <input
                                type="text"
                                placeholder="Add custom model ID..."
                                className="flex-1 bg-neutral-50 border-2 border-brutal-black px-3 py-1.5 font-mono text-sm"
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    addCustomModel(provider.id, e.currentTarget.value);
                                    e.currentTarget.value = '';
                                  }
                                }}
                              />
                              <button className="bg-brutal-black text-white px-3 font-bold border-2 border-brutal-black">+</button>
                            </div>

                            <div className="max-h-48 overflow-y-auto border-2 border-neutral-200 p-2 bg-neutral-50 space-y-1">
                              {allModels.length === 0 && (
                                <p className="text-xs text-neutral-500 text-center py-4">No models found. Click Verify to fetch.</p>
                              )}
                              {allModels.map(m => (
                                <div key={m.id} className="flex items-center justify-between p-1 hover:bg-white hover:shadow-sm border border-transparent hover:border-neutral-200 transition-all">
                                  <span className="text-xs font-mono truncate max-w-[70%]" title={m.id}>{m.name || m.id}</span>
                                  <label className="relative inline-flex items-center cursor-pointer">
                                    <input
                                      type="checkbox"
                                      className="sr-only peer"
                                      checked={conf.enabled_models.includes(m.id)}
                                      onChange={() => toggleModel(provider.id, m.id)}
                                    />
                                    <div className="w-8 h-4 bg-neutral-300 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-brutal-black rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[0px] after:left-[0px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-brutal-green border-2 border-brutal-black"></div>
                                  </label>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="mt-8 bg-brutal-blue/10 border-2 border-brutal-blue border-dashed p-4">
              <p className="text-brutal-black text-sm font-bold uppercase flex items-center gap-2">
                SECURITY NOTICE
              </p>
              <p className="text-xs font-mono mt-1 text-neutral-700">
                Keys are encrypted at rest locally. Use "Verify" to fetch models from provider.
              </p>
            </div>
          </div>
        </div>

        <div className="border-t-4 border-brutal-black p-6 bg-white flex justify-end gap-4 z-10">
          <button
            onClick={onClose}
            className="px-8 py-3 border-2 border-brutal-black font-bold uppercase text-brutal-black hover:bg-neutral-100 transition-colors shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-8 py-3 bg-brutal-black border-2 border-brutal-black font-bold uppercase text-white hover:bg-neutral-800 transition-colors shadow-[4px_4px_0px_0px_rgba(0,0,0,0.5)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-[2px_2px_0px_0px_rgba(0,0,0,0.5)] disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
}
