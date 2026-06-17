import React, { useEffect, useRef, useState } from 'react';

import { useChatStore } from '../../hooks/useChatStore';
import { ApiProvider, CustomProviderPayload, deleteCustomProvider, fetchApiKeys, fetchRoleModels, fetchRoleSuggestions, fetchSocialConfig, fetchMcpServers, saveApiKeys, saveCustomProvider, saveGlobalSandboxConfig, saveRoleModels, saveSocialConfig, saveUserPreferences, SocialConfig, UserConfig, verifyProvider } from '../../lib/api';
import { AppearanceTab } from './AppearanceTab';
import { AutomationTab } from './AutomationTab';
import { DataTab } from './DataTab';
import { McpTab } from './McpTab';
import { MemoryTab } from './MemoryTab';
import { ModelRolesTab } from './ModelRolesTab';
import { ProvidersTab } from './ProvidersTab';
import { SocialTab } from './SocialTab';
import { UsageTab } from './UsageTab';
import { SecurityTab } from './SecurityTab';
import { useI18n, type Locale } from '../../i18n';
import { BrutalSelect } from '../BrutalSelect';

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
  initialCategory?: CategoryType;
}

type ProviderTab = 'credentials' | 'models';
type CategoryType = 'providers' | 'roles' | 'memory' | 'security' | 'social' | 'mcp' | 'automation' | 'data' | 'usage' | 'appearance';

export function SettingsModal({ isOpen, onClose, initialCategory = 'providers' }: SettingsModalProps): React.ReactElement | null {
  const { refreshBackendConfig, backendConfig } = useChatStore();
  const { t, locale, setLocale } = useI18n();
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  // Tracks the original display values returned by the backend so save/verify can skip unchanged keys
  const [originalDisplayValues, setOriginalDisplayValues] = useState<Record<string, string>>({});
  const [userConfigs, setUserConfigs] = useState<Record<string, UserConfig>>({});
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [activeTabs, setActiveTabs] = useState<Record<string, ProviderTab>>({});
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [providersLoaded, setProvidersLoaded] = useState(false);
  const [rolesLoaded, setRolesLoaded] = useState(false);
  const [socialLoaded, setSocialLoaded] = useState(false);
  const [notebookLoaded, setNotebookLoaded] = useState(false);
  const providersAutosaveStarted = useRef(false);
  const rolesAutosaveStarted = useRef(false);
  const socialAutosaveStarted = useRef(false);
  const notebookAutosaveStarted = useRef(false);

  // Role models + suggestions
  const [roleModels, setRoleModels] = useState<Record<string, string[]>>({});
  const [roleSuggestions, setRoleSuggestions] = useState<Record<string, string[]>>({});

  const [activeCategory, setActiveCategory] = useState<CategoryType>('providers');

  // Social Config State
  const [socialConfig, setSocialConfig] = useState<SocialConfig>({ allowed_users: [] });
  const [mcpServers, setMcpServers] = useState<{ urls: Record<string, string>; stdio: Record<string, any>; enabled: Record<string, boolean> } | null>(null);
  const [useCustomTools, setUseCustomTools] = useState(false);
  const [useCustomMcp, setUseCustomMcp] = useState(false);
  const [globalNotebookHostPath, setGlobalNotebookHostPath] = useState('');
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [sandboxEnabled, setSandboxEnabled] = useState(false);

  // MCP Server Management State
  const [mcpServerList, setMcpServerList] = useState<MCPServer[]>([]);

  function refreshProviders(): void {
    fetchApiKeys().then(data => {
      if (!data?.providers) return;
      setProviders(data.providers);
      const keys: Record<string, string> = {};
      const configs: Record<string, UserConfig> = {};
      for (const provider of data.providers) {
        for (const field of provider.fields) {
          if (field.value) keys[field.key] = field.value;
        }
        configs[provider.id] = provider.user_config || { enabled_models: [], custom_models: [] };
      }
      setApiKeys(keys);
      setOriginalDisplayValues({ ...keys });
      setUserConfigs(configs);
    });
  }

  useEffect(() => {
    if (!isOpen) return;

    setActiveCategory(initialCategory);
    setProvidersLoaded(false);
    setRolesLoaded(false);
    setSocialLoaded(false);
    setNotebookLoaded(false);
    providersAutosaveStarted.current = false;
    rolesAutosaveStarted.current = false;
    socialAutosaveStarted.current = false;
    notebookAutosaveStarted.current = false;

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
      setOriginalDisplayValues({ ...initialKeys });
      setUserConfigs(initialConfigs);
      setActiveTabs(initialTabs);
      setProvidersLoaded(true);
      setLoading(false);
    });

    fetchRoleModels().then(models => {
      setRoleModels(models);
      setRolesLoaded(true);
    });
    fetchRoleSuggestions().then(setRoleSuggestions);

    fetchSocialConfig().then(config => {
      setSocialConfig(config);
      setUseCustomTools(config.tools !== null && config.tools !== undefined);
      setUseCustomMcp(config.mcp_enabled !== null && config.mcp_enabled !== undefined);
      setSocialLoaded(true);
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

    const globalVolumes = backendConfig?.globalSandboxVolumes || [];
    const notebookVolume = globalVolumes.find((volume) => {
      const lastColon = volume.lastIndexOf(':');
      if (lastColon === -1) return false;
      return volume.substring(lastColon + 1) === '/mnt/notebook';
    });
    if (notebookVolume) {
      const lastColon = notebookVolume.lastIndexOf(':');
      setGlobalNotebookHostPath(notebookVolume.substring(0, lastColon));
    } else {
      setGlobalNotebookHostPath('');
    }
    setNotebookLoaded(true);
    setMemoryEnabled(!!(backendConfig?.userPreferences?.memory_enabled));
    setSandboxEnabled(!!(backendConfig?.userPreferences?.sandbox_enabled ?? backendConfig?.sandboxEnabled));
  }, [isOpen, initialCategory]);

  async function saveProviderSettings(): Promise<void> {
    const keysToSave: Record<string, string> = {};
    for (const [key, value] of Object.entries(apiKeys)) {
      if (value === originalDisplayValues[key]) continue;
      keysToSave[key] = value;
    }

    await saveApiKeys({
      ...keysToSave,
      "_PROVIDER_CONFIG_": JSON.stringify(userConfigs),
    });
    if (Object.keys(keysToSave).length > 0) {
      setOriginalDisplayValues(prev => ({ ...prev, ...keysToSave }));
    }
  }

  async function saveSocialSettings(): Promise<void> {
    const socialToSave = { ...socialConfig };
    delete socialToSave.model;
    await saveSocialConfig(socialToSave);
  }

  async function handleSandboxEnabledChange(enabled: boolean): Promise<void> {
    setSandboxEnabled(enabled);
    try {
      await saveUserPreferences({ sandbox_enabled: enabled });
      await refreshBackendConfig();
    } catch (error) {
      console.error('Failed to save sandbox setting', error);
      setSandboxEnabled(!enabled);
    }
  }

  async function handleMemoryEnabledChange(enabled: boolean): Promise<void> {
    setMemoryEnabled(enabled);
    try {
      await saveUserPreferences({ memory_enabled: enabled });
      await refreshBackendConfig();
    } catch (error) {
      console.error('Failed to save memory setting', error);
      setMemoryEnabled(!enabled);
    }
  }

  async function saveNotebookSettings(): Promise<void> {
    const sandboxVolumes = globalNotebookHostPath.trim()
      ? [`${globalNotebookHostPath.trim()}:/mnt/notebook`]
      : [];

    await saveGlobalSandboxConfig(sandboxVolumes);
    await refreshBackendConfig();
  }

  async function handleClose(): Promise<void> {
    try {
      await Promise.all([
        providersLoaded ? saveProviderSettings() : Promise.resolve(),
        rolesLoaded ? saveRoleModels(roleModels) : Promise.resolve(),
        socialLoaded ? saveSocialSettings() : Promise.resolve(),
        notebookLoaded ? saveNotebookSettings() : Promise.resolve(),
      ]);
    } catch (error) {
      console.error('Failed to save settings before close', error);
    } finally {
      onClose();
    }
  }

  useEffect(() => {
    if (!isOpen || !providersLoaded) return;
    if (!providersAutosaveStarted.current) {
      providersAutosaveStarted.current = true;
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        await saveProviderSettings();
      } catch (error) {
        console.error('Failed to save provider settings', error);
      }
    }, 600);

    return () => window.clearTimeout(timeoutId);
  }, [apiKeys, userConfigs, isOpen, providersLoaded]);

  useEffect(() => {
    if (!isOpen || !rolesLoaded) return;
    if (!rolesAutosaveStarted.current) {
      rolesAutosaveStarted.current = true;
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        await saveRoleModels(roleModels);
      } catch (error) {
        console.error('Failed to save model roles', error);
      }
    }, 600);

    return () => window.clearTimeout(timeoutId);
  }, [roleModels, isOpen, rolesLoaded]);

  useEffect(() => {
    if (!isOpen || !socialLoaded) return;
    if (!socialAutosaveStarted.current) {
      socialAutosaveStarted.current = true;
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        await saveSocialSettings();
      } catch (error) {
        console.error('Failed to save social settings', error);
      }
    }, 600);

    return () => window.clearTimeout(timeoutId);
  }, [socialConfig, isOpen, socialLoaded]);

  useEffect(() => {
    if (!isOpen || !notebookLoaded) return;
    if (!notebookAutosaveStarted.current) {
      notebookAutosaveStarted.current = true;
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        await saveNotebookSettings();
      } catch (error) {
        console.error('Failed to save notebook settings', error);
      }
    }, 600);

    return () => window.clearTimeout(timeoutId);
  }, [globalNotebookHostPath, isOpen, notebookLoaded, refreshBackendConfig]);

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
      if (val && val !== originalDisplayValues[field.key]) {
        configForProvider[field.key] = val;
      }
    }

    const result = await verifyProvider(provider.id, configForProvider);

    if (result.success && result.models.length > 0) {
      setProviders(prev => prev.map(p =>
        p.id === provider.id ? { ...p, models: result.models } : p
      ));
    } else {
      alert(t('settings.verifyFailed'));
    }

    setVerifying(prev => ({ ...prev, [provider.id]: false }));
  }

  if (!isOpen) return null;

  const categories = [
    {
      id: 'providers', label: t('settings.categories.providers'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
      )
    },
    {
      id: 'roles', label: t('settings.categories.roles'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
        </svg>
      )
    },
    {
      id: 'memory', label: t('settings.categories.memory'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      )
    },
    {
      id: 'security', label: t('settings.categories.security'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      )
    },
    {
      id: 'social', label: t('settings.categories.social'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      )
    },
    {
      id: 'mcp', label: t('settings.categories.mcp'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
      )
    },
    {
      id: 'automation', label: t('settings.categories.automation'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    },
    {
      id: 'data', label: t('settings.categories.data'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 7c0 1.657 3.582 3 8 3s8-1.343 8-3M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3M4 7v10c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 12c0 1.657 3.582 3 8 3s8-1.343 8-3" />
        </svg>
      )
    },
    {
      id: 'usage', label: t('settings.categories.usage'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    },
    {
      id: 'appearance', label: t('settings.categories.appearance'), icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
        </svg>
      )
    },
  ];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center animate-view-fade">
      <div className="absolute inset-0 bg-brutal-black/80 backdrop-blur-sm" onClick={handleClose} />

      <div className="relative w-full h-[95vh] md:w-[95vw] lg:w-[85vw] xl:w-[75vw] bg-neutral-100 dark:bg-zinc-900 border-4 border-brutal-black shadow-brutal-xl flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-white dark:bg-zinc-800 border-r-4 border-brutal-black flex flex-col flex-shrink-0">
          <div className="p-6 border-b-4 border-brutal-black bg-brutal-yellow dark:bg-brutal-yellow">
            <h1 className="text-2xl font-brutal font-bold uppercase tracking-tighter text-brutal-black">
              {t('settings.usingSuzent')}
            </h1>
          </div>

          {/* Language Selector */}
          <div className="px-4 pt-4 pb-2 border-b-2 border-neutral-200">
            <BrutalSelect
              value={locale}
              onChange={(val) => setLocale(val as Locale)}
              options={[
                { value: 'en', label: 'English' },
                { value: 'zh-CN', label: '简体中文' },
              ]}
              label={t('settings.language')}
            />
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {categories.map(item => (
              <button
                key={item.id}
                onClick={() => setActiveCategory(item.id as CategoryType)}
                className={`w-full text-left px-4 py-3 border-2 font-bold uppercase text-sm flex items-center gap-3 transition-all shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none ${activeCategory === item.id
                  ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black border-brutal-black'
                  : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white border-brutal-black hover:bg-neutral-100 dark:hover:bg-zinc-600'
                  }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>

          <div className="p-4 border-t-4 border-brutal-black bg-neutral-50 dark:bg-zinc-800">
            <button
              onClick={handleClose}
              className="w-full px-4 py-3 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none"
            >
              {t('common.close')}
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
                      onAddProvider={async (payload: CustomProviderPayload) => {
                        const result = await saveCustomProvider(payload);
                        if (!result.success) throw new Error(result.error || 'Failed to save');
                        const data = await fetchApiKeys();
                        if (data?.providers) {
                          setProviders(data.providers);
                          const configs: Record<string, UserConfig> = {};
                          const tabs: Record<string, 'credentials' | 'models'> = {};
                          for (const p of data.providers) {
                            configs[p.id] = p.user_config || { enabled_models: [], custom_models: [] };
                            tabs[p.id] = activeTabs[p.id] || 'credentials';
                          }
                          setUserConfigs(configs);
                          setActiveTabs(tabs);
                        }
                      }}
                      onDeleteProvider={async (providerId: string) => {
                        await deleteCustomProvider(providerId);
                        setProviders(prev => prev.filter(p => p.id !== providerId));
                      }}
                      onChatGPTAuthChanged={refreshBackendConfig}
                    />
                  )}

                  {activeCategory === 'roles' && (
                    <ModelRolesTab
                      roleModels={roleModels}
                      suggestions={roleSuggestions}
                      onChange={setRoleModels}
                    />
                  )}

                  {activeCategory === 'memory' && (
                    <MemoryTab
                      globalNotebookHostPath={globalNotebookHostPath}
                      onGlobalNotebookHostPathChange={setGlobalNotebookHostPath}
                      memoryEnabled={memoryEnabled}
                      onMemoryEnabledChange={handleMemoryEnabledChange}
                      embeddingModel={backendConfig?.userPreferences?.embedding_model}
                      extractionModel={backendConfig?.userPreferences?.extraction_model}
                    />
                  )}

                  {activeCategory === 'security' && (
                    <SecurityTab
                      sandboxEnabled={sandboxEnabled}
                      onSandboxEnabledChange={handleSandboxEnabledChange}
                    />
                  )}

                  {activeCategory === 'social' && (
                    <SocialTab
                      socialConfig={socialConfig}
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

                  {activeCategory === 'automation' && (
                    <AutomationTab
                      models={backendConfig?.models || []}
                      tools={backendConfig?.tools || []}
                    />
                  )}

                  {activeCategory === 'data' && (
                    <DataTab onSyncComplete={refreshProviders} />
                  )}

                  {activeCategory === 'usage' && (
                    <UsageTab />
                  )}

                  {activeCategory === 'appearance' && (
                    <AppearanceTab />
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
