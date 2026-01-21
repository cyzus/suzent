import React, { useEffect, useState } from 'react';

import { useChatStore } from '../../hooks/useChatStore';
import { ApiProvider, fetchApiKeys, fetchEmbeddingModels, saveApiKeys, saveUserPreferences, UserConfig, verifyProvider } from '../../lib/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalSelect } from '../BrutalSelect';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type ProviderTab = 'credentials' | 'models';

export function SettingsModal({ isOpen, onClose }: SettingsModalProps): React.ReactElement | null {
  const { refreshBackendConfig, backendConfig } = useChatStore();
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [userConfigs, setUserConfigs] = useState<Record<string, UserConfig>>({});
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [activeTabs, setActiveTabs] = useState<Record<string, ProviderTab>>({});
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Memory Configuration state
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [selectedEmbeddingModel, setSelectedEmbeddingModel] = useState<string>('');
  const [selectedExtractionModel, setSelectedExtractionModel] = useState<string>('');
  const [activeCategory, setActiveCategory] = useState<'providers' | 'memory'>('providers');

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

    // Fetch embedding models
    fetchEmbeddingModels().then(models => {
      setEmbeddingModels(models);
    });

    // Initialize from existing preferences
    const prefs = (backendConfig as any)?.userPreferences;
    if (prefs) {
      setSelectedEmbeddingModel(prefs.embedding_model || '');
      setSelectedExtractionModel(prefs.extraction_model || '');
    }
  }, [isOpen, backendConfig]);

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

    // Save memory configuration preferences
    if (selectedEmbeddingModel || selectedExtractionModel) {
      await saveUserPreferences({
        embedding_model: selectedEmbeddingModel || undefined,
        extraction_model: selectedExtractionModel || undefined,
      });
    }

    await refreshBackendConfig();

    setSaving(false);
    onClose();
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center animate-view-fade">
      <div className="absolute inset-0 bg-brutal-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full h-[95vh] md:w-[95vw] lg:w-[85vw] xl:w-[75vw] bg-neutral-100 border-4 border-brutal-black shadow-brutal-xl flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-white border-r-4 border-brutal-black flex flex-col flex-shrink-0">
          <div className="p-6 border-b-4 border-brutal-black bg-brutal-yellow">
            <h1 className="text-2xl font-brutal font-bold uppercase tracking-tighter text-brutal-black">
              Using Suzent
            </h1>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {[
              {
                id: 'providers', label: 'Model Providers', icon: (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                )
              },
              {
                id: 'memory', label: 'Memory System', icon: (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                )
              }
            ].map(item => (
              <button
                key={item.id}
                onClick={() => setActiveCategory(item.id as any)}
                className={`w-full text-left px-4 py-3 border-2 font-bold uppercase text-sm flex items-center gap-3 transition-all shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none ${activeCategory === item.id
                  ? 'bg-brutal-black text-white border-brutal-black'
                  : 'bg-white text-brutal-black border-brutal-black hover:bg-neutral-100'
                  }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>

          <div className="p-4 border-t-4 border-brutal-black bg-neutral-50">
            <button
              onClick={onClose}
              className="w-full px-4 py-3 bg-white border-2 border-brutal-black font-bold uppercase text-brutal-black hover:bg-neutral-100 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none mb-3"
            >
              Close
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full px-4 py-3 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-brutal-black hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50 flex justify-center items-center gap-2"
            >
              {saving ? (
                <>
                  <div className="animate-spin h-4 w-4 border-2 border-brutal-black border-t-transparent rounded-full"></div>
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden bg-dot-pattern flex flex-col">
          <div className="flex-1 overflow-y-auto p-8 scrollbar-thin">
            <div className="max-w-4xl mx-auto">
              {loading ? (
                <div className="flex justify-center items-center h-full">
                  <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-brutal-black"></div>
                </div>
              ) : (
                <>
                  {activeCategory === 'providers' && (
                    <div className="space-y-6">
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black">Model Providers</h2>
                      </div>

                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                        {providers.map((provider) => {
                          const activeTab = activeTabs[provider.id] || 'credentials'; // Default to credentials
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
                                  onClick={() => setActiveTabs(p => ({ ...p, [provider.id]: 'credentials' }))}
                                  className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors ${activeTab === 'credentials' ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                >
                                  API Keys
                                </button>
                                <button
                                  onClick={() => setActiveTabs(p => ({ ...p, [provider.id]: 'models' }))}
                                  className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors ${activeTab === 'models' ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}`}
                                >
                                  Models
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
                                                onChange={(e) => handleKeyChange(field.key, e.target.value)}
                                                placeholder={field.placeholder}
                                                className={`w-full bg-white border-2 border-brutal-black border-r-0 px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 transition-all ${isMasked ? 'text-neutral-500 italic' : ''}`}
                                              />
                                            </div>
                                            {field.type === 'secret' && (
                                              <button
                                                onClick={() => setShowKey(prev => ({ ...prev, [field.key]: !prev[field.key] }))}
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
                                          placeholder="Add model ID..."
                                          className="flex-1 bg-white border-2 border-brutal-black border-r-0 px-3 py-2 font-mono text-xs focus:outline-none"
                                          onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                              addCustomModel(provider.id, e.currentTarget.value);
                                              e.currentTarget.value = '';
                                            }
                                          }}
                                        />
                                        <button className="bg-brutal-black text-white w-10 font-bold border-2 border-brutal-black hover:bg-neutral-800 flex items-center justify-center text-lg">+</button>
                                      </div>
                                      <button
                                        onClick={() => handleVerify(provider)}
                                        disabled={verifying[provider.id]}
                                        className="text-xs bg-brutal-blue text-white px-4 py-2 font-black uppercase border-2 border-brutal-black hover:translate-y-0.5 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none transition-all disabled:opacity-50 shrink-0"
                                      >
                                        {verifying[provider.id] ? 'FETCHING...' : 'FETCH'}
                                      </button>
                                    </div>

                                    {/* Models List (Scrollable) */}
                                    <BrutalMultiSelect
                                      variant="list"
                                      value={conf.enabled_models}
                                      onChange={(newVal) => setUserConfigs(prev => ({ ...prev, [provider.id]: { ...conf, enabled_models: newVal } }))}
                                      options={allModels.map(m => ({ value: m.id, label: m.name || m.id }))}
                                      emptyMessage="No models found"
                                      emptyAction={
                                        <button onClick={() => handleVerify(provider)} className="underline hover:text-black">Fetch Models</button>
                                      }
                                      dropdownClassName="max-h-80"
                                    />

                                    {/* Footer */}
                                    <div className="flex justify-between items-center px-1 mt-2">
                                      <span className="text-[10px] text-neutral-500 font-bold uppercase tracking-wider">{allModels.length} AVAILABLE</span>
                                    </div>

                                  </div>
                                )
                                }
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {activeCategory === 'memory' && (
                    <div className="space-y-6">
                      <h2 className="text-3xl font-brutal font-black uppercase text-brutal-black">Memory Configuration</h2>
                      <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
                        <div className="flex items-start gap-4 mb-6">
                          <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
                          </div>
                          <div>
                            <h3 className="text-xl font-bold uppercase">System Configuration</h3>
                            <p className="text-sm text-neutral-600 mt-1">Configure user preferences for memory and extraction. Changes here require a server restart to take full effect.</p>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 gap-6">
                          {/* Extraction Model */}
                          <div className="space-y-2">
                            <label className="text-sm font-bold uppercase text-neutral-800 flex justify-between">
                              Extraction Model
                              <span className="text-[10px] bg-neutral-200 px-2 py-0.5 border border-brutal-black">For Logic/Fact Extraction</span>
                            </label>
                            <BrutalSelect
                              value={selectedExtractionModel}
                              onChange={setSelectedExtractionModel}
                              options={[
                                { value: '', label: 'Use heuristics (no LLM)' },
                                ...((backendConfig?.models || []).map((model: string) => ({ value: model, label: model })))
                              ]}
                              placeholder="SELECT EXTRACTION MODEL..."
                              className="z-20"
                            />
                          </div>

                          {/* Embedding Model */}
                          <div className="space-y-2">
                            <label className="text-sm font-bold uppercase text-neutral-800 flex justify-between">
                              Embedding Model
                              <span className="text-[10px] bg-neutral-200 px-2 py-0.5 border border-brutal-black">For Vector Search</span>
                            </label>
                            <BrutalSelect
                              value={selectedEmbeddingModel}
                              onChange={setSelectedEmbeddingModel}
                              options={[
                                { value: '', label: 'None (Default)' },
                                ...embeddingModels.map((model) => ({ value: model, label: model }))
                              ]}
                              placeholder="SELECT EMBEDDING MODEL..."
                              className="z-10"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}


                </>
              )}
            </div>
          </div>
        </div>
      </div >
    </div >
  );
}
