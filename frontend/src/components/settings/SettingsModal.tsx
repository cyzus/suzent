import React, { useEffect, useRef, useState } from 'react';

import { useChatStore } from '../../hooks/useChatStore';
import { ApiProvider, CustomProviderPayload, deleteCustomProvider, fetchApiKeys, fetchRoleModels, fetchRoleSuggestions, fetchSocialConfig, fetchMcpServers, saveApiKeys, saveCustomProvider, saveGlobalSandboxConfig, saveRoleModels, saveSocialConfig, saveUserPreferences, SocialConfig, UserConfig, verifyProvider } from '../../lib/api';
import { AcpAgentsTab } from './AcpAgentsTab';
import { AppearanceTab } from './AppearanceTab';
import { AboutTab } from './AboutTab';
import { AutomationTab } from './AutomationTab';
import { DataTab } from './DataTab';
import { McpTab } from './McpTab';
import { MemoryTab } from './MemoryTab';
import { ModelRolesTab } from './ModelRolesTab';
import { ProvidersTab } from './ProvidersTab';
import { SocialTab } from './SocialTab';
import { DevicesTab } from './DevicesTab';
import { MeshTab } from './MeshTab';
import { UsageTab } from './UsageTab';
import { SecurityTab } from './SecurityTab';
import { BackgroundServiceTab } from './BackgroundServiceTab';
import { useI18n } from '../../i18n';
import { FullscreenOverlay } from '../FullscreenOverlay';
import { closeImmediatelyAndPersist } from './settingsPersistence';
import {
  SettingsMobileNavigation,
  SettingsNavigation,
  type SettingsCategory,
} from './SettingsNavigation';

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
type CategoryType = SettingsCategory;

export function SettingsModal({ isOpen, onClose, initialCategory = 'providers' }: SettingsModalProps): React.ReactElement | null {
  const { refreshBackendConfig, backendConfig } = useChatStore();
  const { t } = useI18n();
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
  const savedProviderSnapshot = useRef<string | null>(null);
  const savedRolesSnapshot = useRef<string | null>(null);
  const savedSocialSnapshot = useRef<string | null>(null);
  const savedNotebookPath = useRef<string | null>(null);

  // Role models + suggestions
  const [roleModels, setRoleModels] = useState<Record<string, string[]>>({});
  const [roleSuggestions, setRoleSuggestions] = useState<Record<string, string[]>>({});

  const [activeCategory, setActiveCategory] = useState<CategoryType>('providers');

  // Social Config State
  const [socialConfig, setSocialConfig] = useState<SocialConfig>({});
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
      savedProviderSnapshot.current = JSON.stringify({ apiKeys: keys, userConfigs: configs });
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
    savedProviderSnapshot.current = null;
    savedRolesSnapshot.current = null;
    savedSocialSnapshot.current = null;
    savedNotebookPath.current = null;

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
      savedProviderSnapshot.current = JSON.stringify({
        apiKeys: initialKeys,
        userConfigs: initialConfigs,
      });
      setProvidersLoaded(true);
      setLoading(false);
    });

    fetchRoleModels().then(models => {
      setRoleModels(models);
      savedRolesSnapshot.current = JSON.stringify(models);
      setRolesLoaded(true);
    });
    fetchRoleSuggestions().then(setRoleSuggestions);

    fetchSocialConfig().then(config => {
      setSocialConfig(config);
      setUseCustomTools(config.tools !== null && config.tools !== undefined);
      setUseCustomMcp(config.mcp_enabled !== null && config.mcp_enabled !== undefined);
      const socialSnapshot = { ...config };
      delete socialSnapshot.model;
      savedSocialSnapshot.current = JSON.stringify(socialSnapshot);
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
    savedNotebookPath.current = notebookVolume
      ? notebookVolume.substring(0, notebookVolume.lastIndexOf(':')).trim()
      : '';
    setNotebookLoaded(true);
    setMemoryEnabled(!!(backendConfig?.userPreferences?.memory_enabled));
    setSandboxEnabled(!!(backendConfig?.userPreferences?.sandbox_enabled ?? backendConfig?.sandboxEnabled));
  }, [isOpen, initialCategory]);

  async function saveProviderSettings(): Promise<void> {
    const snapshot = JSON.stringify({ apiKeys, userConfigs });
    if (snapshot === savedProviderSnapshot.current) return;

    const keysToSave: Record<string, string> = {};
    for (const [key, value] of Object.entries(apiKeys)) {
      if (value === originalDisplayValues[key]) continue;
      keysToSave[key] = value;
    }

    const saved = await saveApiKeys({
      ...keysToSave,
      "_PROVIDER_CONFIG_": JSON.stringify(userConfigs),
    });
    if (!saved) throw new Error('Failed to save provider settings');

    savedProviderSnapshot.current = snapshot;
    if (Object.keys(keysToSave).length > 0) {
      setOriginalDisplayValues(prev => ({ ...prev, ...keysToSave }));
    }

    // Enabling/disabling provider models changes what the rest of the app can
    // offer: the chat engine picker reads backendConfig.models and the Model
    // Roles dropdown reads the role suggestions. Both are derived server-side
    // from the enabled models we just wrote, so re-pull them here instead of
    // waiting for the next app reload.
    await Promise.allSettled([
      refreshBackendConfig(),
      fetchRoleSuggestions().then(setRoleSuggestions),
    ]);
  }

  async function saveSocialSettings(): Promise<void> {
    const socialToSave = { ...socialConfig };
    delete socialToSave.model;
    const snapshot = JSON.stringify(socialToSave);
    if (snapshot === savedSocialSnapshot.current) return;

    const saved = await saveSocialConfig(socialToSave);
    if (!saved) throw new Error('Failed to save social settings');
    savedSocialSnapshot.current = snapshot;
  }

  async function saveRoleSettings(): Promise<void> {
    const snapshot = JSON.stringify(roleModels);
    if (snapshot === savedRolesSnapshot.current) return;

    const saved = await saveRoleModels(roleModels);
    if (!saved) throw new Error('Failed to save model roles');
    savedRolesSnapshot.current = snapshot;
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
    const notebookPath = globalNotebookHostPath.trim();
    if (notebookPath === savedNotebookPath.current) return;

    const sandboxVolumes = notebookPath
      ? [`${notebookPath}:/mnt/notebook`]
      : [];

    await saveGlobalSandboxConfig(sandboxVolumes);
    savedNotebookPath.current = notebookPath;
    await refreshBackendConfig();
  }

  function handleClose(): void {
    closeImmediatelyAndPersist(
      onClose,
      async () => {
        const results = await Promise.allSettled([
          providersLoaded ? saveProviderSettings() : Promise.resolve(),
          rolesLoaded ? saveRoleSettings() : Promise.resolve(),
          socialLoaded ? saveSocialSettings() : Promise.resolve(),
          notebookLoaded ? saveNotebookSettings() : Promise.resolve(),
        ]);

        for (const result of results) {
          if (result.status === 'rejected') {
            console.error('Failed to save settings after close', result.reason);
          }
        }
      },
      error => console.error('Failed to persist settings after close', error),
    );
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
        await saveRoleSettings();
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
      alert(result.message || result.error || t('settings.verifyFailed'));
    }

    setVerifying(prev => ({ ...prev, [provider.id]: false }));
  }

  if (!isOpen) return null;


  return (
    <FullscreenOverlay
      open={isOpen}
      onClose={handleClose}
      zIndexClassName="z-[100]"
      backdropClassName="bg-brutal-black/80 backdrop-blur-sm animate-view-fade"
      containerClassName="relative w-full h-[95vh] md:w-[95vw] lg:w-[90vw] xl:w-[82vw] 2xl:max-w-[1600px] bg-neutral-100 dark:bg-zinc-900 border-4 border-brutal-black shadow-brutal-xl flex overflow-hidden"
    >
        <SettingsNavigation
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
          onClose={handleClose}
        />

        {/* Content Area */}
        <div className="flex-1 overflow-hidden bg-dot-pattern flex flex-col">
          <SettingsMobileNavigation
            activeCategory={activeCategory}
            onCategoryChange={setActiveCategory}
            onClose={handleClose}
          />
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 scrollbar-thin">
            <div className={`${activeCategory === 'usage' ? 'max-w-6xl' : 'max-w-4xl'} mx-auto`}>
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
                      embeddingModel={roleModels.embedding?.[0]}
                      cheapModel={roleModels.cheap?.[0]}
                      onOpenModelRoles={() => setActiveCategory('roles')}
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

                  {activeCategory === 'devices' && (
                    <DevicesTab />
                  )}

                  {activeCategory === 'mesh' && (
                    <MeshTab />
                  )}

                  {activeCategory === 'mcp' && (
                    <McpTab
                      serverList={mcpServerList}
                      onServerListChange={setMcpServerList}
                      onMcpServersRefresh={setMcpServers}
                    />
                  )}

                  {activeCategory === 'acp-agents' && (
                    <AcpAgentsTab />
                  )}

                  {activeCategory === 'automation' && (
                    <AutomationTab
                      models={backendConfig?.models || []}
                      tools={backendConfig?.tools || []}
                    />
                  )}

                  {activeCategory === 'service' && (
                    <BackgroundServiceTab />
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

                  {activeCategory === 'about' && (
                    <AboutTab />
                  )}
                </>
              )}
            </div>
          </div>
        </div>
    </FullscreenOverlay>
  );
}
