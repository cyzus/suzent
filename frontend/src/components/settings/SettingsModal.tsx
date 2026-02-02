import React, { useEffect, useState } from 'react';

import { useChatStore } from '../../hooks/useChatStore';
import { ApiProvider, fetchApiKeys, fetchEmbeddingModels, fetchSocialConfig, fetchMcpServers, saveApiKeys, saveSocialConfig, saveUserPreferences, SocialConfig, UserConfig, verifyProvider } from '../../lib/api';
import { McpTab } from './McpTab';
import { MemoryTab } from './MemoryTab';
import { ProvidersTab } from './ProvidersTab';
import { SocialTab } from './SocialTab';

type MCPUrlServer = {
  type: 'url';
  name: string;
  url: string;
  enabled: boolean;
};

type MCPStdioServer = {
  type: 'stdio';
  name: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
  enabled: boolean;
};

type MCPServer = MCPUrlServer | MCPStdioServer;

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type ProviderTab = 'credentials' | 'models';
type CategoryType = 'providers' | 'memory' | 'social' | 'mcp';

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
  const [activeCategory, setActiveCategory] = useState<CategoryType>('providers');

  // Social Config State
  const [socialConfig, setSocialConfig] = useState<SocialConfig>({ allowed_users: [] });
  const [mcpServers, setMcpServers] = useState<{ urls: Record<string, string>; stdio: Record<string, any>; enabled: Record<string, boolean> } | null>(null);
  const [useCustomTools, setUseCustomTools] = useState(false);
  const [useCustomMcp, setUseCustomMcp] = useState(false);

  // MCP Server Management State
  const [mcpServerList, setMcpServerList] = useState<MCPServer[]>([]);

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

    fetchEmbeddingModels().then(models => {
      setEmbeddingModels(models);
    });

    fetchSocialConfig().then(config => {
      setSocialConfig(config);
      setUseCustomTools(config.tools !== null && config.tools !== undefined);
      setUseCustomMcp(config.mcp_enabled !== null && config.mcp_enabled !== undefined);
    });

    fetchMcpServers().then(data => {
      setMcpServers(data);
      const urls = data.urls || {};
      const stdio = data.stdio || {};
      const enabled = data.enabled || {};

      const urlServers: MCPServer[] = Object.entries(urls).map(([name, url]) => ({
        type: 'url',
        name,
        url: String(url),
        enabled: !!enabled[name]
      }));

      const stdioServers: MCPServer[] = Object.entries(stdio).map(([name, params]: [string, any]) => ({
        type: 'stdio',
        name,
        command: params.command,
        args: params.args,
        env: params.env,
        enabled: !!enabled[name],
      }));

      setMcpServerList([...urlServers, ...stdioServers]);
    }).catch(() => setMcpServers(null));

    const prefs = (backendConfig as any)?.userPreferences;
    if (prefs) {
      setSelectedEmbeddingModel(prefs.embedding_model || '');
      setSelectedExtractionModel(prefs.extraction_model || '');
    }
  }, [isOpen, backendConfig]);

  function handleKeyChange(key: string, val: string): void {
    setApiKeys(prev => ({ ...prev, [key]: val }));
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

    if (selectedEmbeddingModel || selectedExtractionModel) {
      await saveUserPreferences({
        embedding_model: selectedEmbeddingModel || undefined,
        extraction_model: selectedExtractionModel || undefined,
      });
    }

    await saveSocialConfig(socialConfig);
    await refreshBackendConfig();

    setSaving(false);
    onClose();
  }

  if (!isOpen) return null;

  const categories = [
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
    },
    {
      id: 'social', label: 'Social Channels', icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      )
    },
    {
      id: 'mcp', label: 'MCP Servers', icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
      )
    }
  ];

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
            {categories.map(item => (
              <button
                key={item.id}
                onClick={() => setActiveCategory(item.id as CategoryType)}
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
                    <ProvidersTab
                      providers={providers}
                      apiKeys={apiKeys}
                      userConfigs={userConfigs}
                      showKey={showKey}
                      activeTabs={activeTabs}
                      verifying={verifying}
                      onKeyChange={handleKeyChange}
                      onToggleShowKey={(key) => setShowKey(prev => ({ ...prev, [key]: !prev[key] }))}
                      onTabChange={(providerId, tab) => setActiveTabs(prev => ({ ...prev, [providerId]: tab }))}
                      onConfigChange={(providerId, config) => setUserConfigs(prev => ({ ...prev, [providerId]: config }))}
                      onAddCustomModel={addCustomModel}
                      onVerify={handleVerify}
                    />
                  )}

                  {activeCategory === 'memory' && (
                    <MemoryTab
                      embeddingModels={embeddingModels}
                      models={backendConfig?.models || []}
                      selectedEmbeddingModel={selectedEmbeddingModel}
                      selectedExtractionModel={selectedExtractionModel}
                      onEmbeddingModelChange={setSelectedEmbeddingModel}
                      onExtractionModelChange={setSelectedExtractionModel}
                    />
                  )}

                  {activeCategory === 'social' && (
                    <SocialTab
                      socialConfig={socialConfig}
                      models={backendConfig?.models || []}
                      tools={backendConfig?.tools || []}
                      mcpServers={mcpServers}
                      useCustomTools={useCustomTools}
                      useCustomMcp={useCustomMcp}
                      onConfigChange={setSocialConfig}
                      onUseCustomToolsChange={setUseCustomTools}
                      onUseCustomMcpChange={setUseCustomMcp}
                    />
                  )}

                  {activeCategory === 'mcp' && (
                    <McpTab
                      serverList={mcpServerList}
                      onServerListChange={setMcpServerList}
                      onMcpServersRefresh={setMcpServers}
                    />
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
