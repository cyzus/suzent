import React, { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

import { useChatStore } from '../../hooks/useChatStore';
import { fetchMcpServers, setMcpServerEnabled } from '../../lib/api';
import { useI18n } from '../../i18n';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
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

export function ConfigView(): React.ReactElement {
  const { config, setConfig, backendConfig } = useChatStore();
  const { t } = useI18n();

  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(false);

  const prevMcpStateRef = useRef<string>('');

  useEffect(() => {
    fetchMcpServers().then(data => {
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

      setServers([...urlServers, ...stdioServers]);
    });
  }, [backendConfig]);

  useEffect(() => {
    // Generate dictionary { [name]: url } for enabled URL servers
    // This allows backend to look up headers by server name
    const enabledUrlDict: Record<string, string> = {};
    servers.forEach(s => {
      if (s.enabled && s.type === 'url') {
        enabledUrlDict[s.name] = s.url;
      }
    });

    const mcp_enabled: Record<string, boolean> = {};
    for (const server of servers) {
      mcp_enabled[server.name] = server.enabled;
    }

    const currentState = JSON.stringify({ enabledUrls: enabledUrlDict, mcp_enabled });
    if (currentState !== prevMcpStateRef.current) {
      prevMcpStateRef.current = currentState;
      setConfig(prevConfig => ({ ...prevConfig, mcp_urls: enabledUrlDict, mcp_enabled }));
    }
  }, [servers, setConfig]);

  const update = useCallback((patch: Partial<typeof config>) => {
    setConfig(prevConfig => ({ ...prevConfig, ...patch }));
  }, [setConfig]);

  function toggleTool(tool: string): void {
    flushSync(() => {
      setConfig(prevConfig => {
        const currentTools = prevConfig.tools || [];
        const isActive = currentTools.includes(tool);
        const newTools = isActive
          ? currentTools.filter((t: string) => t !== tool)
          : [...currentTools, tool];
        return { ...prevConfig, tools: newTools };
      });
    });
  }

  const toggleServer = useCallback(async (name: string) => {
    setLoading(true);
    try {
      const server = servers.find(s => s.name === name);
      if (!server) return;
      await setMcpServerEnabled(name, !server.enabled);
      setServers(prev => prev.map(s =>
        s.name === name ? { ...s, enabled: !s.enabled } : s
      ));
    } finally {
      setLoading(false);
    }
  }, [servers]);



  if (!backendConfig) {
    return <div className="text-xs text-brutal-black font-bold uppercase animate-brutal-blink">{t('config.loading')}</div>;
  }

  return (
    <div className="space-y-6 text-xs">

      <div className="space-y-1">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">{t('config.agentLabel')}</label>
        <BrutalSelect
          value={config.agent}
          onChange={val => update({ agent: val })}
          options={backendConfig.agents}
        />
        <div className="text-xs text-brutal-black mt-1 leading-relaxed font-medium">
          {config.agent === 'CodeAgent' && (
            <span>{t('config.agent.code')}</span>
          )}
          {config.agent === 'ToolcallingAgent' && (
            <span>{t('config.agent.toolcalling')}</span>
          )}
        </div>
      </div>
      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">{t('config.toolsLabel')}</label>
        <BrutalMultiSelect
          variant="list"
          value={config.tools || []}
          onChange={(newTools) => update({ tools: newTools })}
          options={backendConfig.tools
            .filter((t: string) => !['MemorySearchTool', 'MemoryBlockUpdateTool'].includes(t))
            .map((tool: string) => ({
              value: tool,
              label: tool.replace(/Tool$/, '').replace(/([a-z])([A-Z])/g, '$1 $2').toUpperCase()
            }))
          }
          emptyMessage={t('config.toolsEmpty')}
        />
      </div>
      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">{t('config.memory.label')}</label>
        <button
          type="button"
          onClick={() => update({ memory_enabled: !config.memory_enabled })}
          className={`w-full px-3 py-2 border-3 text-xs font-bold uppercase transition-all duration-200 flex items-center justify-between ${config.memory_enabled
            ? 'bg-brutal-green text-brutal-black border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            : 'border-brutal-black text-brutal-black bg-white hover:bg-brutal-yellow hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            }`}
        >
          <span>{t('config.memory.button')}</span>
          <span className={`text-[10px] px-2 py-1 border-2 font-bold ${config.memory_enabled
            ? 'border-brutal-black bg-white text-brutal-black'
            : 'border-brutal-black bg-neutral-200 text-brutal-black'
            }`}>
            {config.memory_enabled ? t('common.enabled') : t('common.disabled')}
          </span>
        </button>
        <div className="text-[11px] text-brutal-black font-medium leading-relaxed">
          {config.memory_enabled ? (
            <span>{t('config.memory.enabledDesc')}</span>
          ) : (
            <span>{t('config.memory.disabledDesc')}</span>
          )}
        </div>
      </div>



      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">{t('config.sandbox.label')}</label>
        <button
          type="button"
          onClick={() => update({ sandbox_enabled: !config.sandbox_enabled })}
          className={`w-full px-3 py-2 border-3 text-xs font-bold uppercase transition-all duration-200 flex items-center justify-between ${config.sandbox_enabled
            ? 'bg-brutal-green text-brutal-black border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            : 'border-brutal-black text-brutal-black bg-white hover:bg-brutal-yellow hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            }`}
        >
          <span>{t('config.sandbox.button')}</span>
          <span className={`text-[10px] px-2 py-1 border-2 font-bold ${config.sandbox_enabled
            ? 'border-brutal-black bg-white text-brutal-black'
            : 'border-brutal-black bg-neutral-200 text-brutal-black'
            }`}>
            {config.sandbox_enabled ? t('common.enabled') : t('common.disabled')}
          </span>
        </button>
        <div className="text-[11px] text-brutal-black font-medium leading-relaxed">
          {config.sandbox_enabled ? (
            <span>{t('config.sandbox.enabledDesc')}</span>
          ) : (
            <span>{t('config.sandbox.disabledDesc')}</span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-[10px] font-bold uppercase text-brutal-black">{t('config.volumeMounts.label')}</div>

        {/* Global volumes from config file (read-only) */}
        {backendConfig?.globalSandboxVolumes && backendConfig.globalSandboxVolumes.length > 0 && (
          <div className="space-y-1">
            <div className="text-[9px] font-bold uppercase text-brutal-black opacity-60">{t('config.volumeMounts.globalFromConfig')}</div>
            <ul className="space-y-1">
              {backendConfig.globalSandboxVolumes.map((vol: string, idx: number) => (
                <li key={`global-${idx}`} className="flex items-center gap-2 bg-brutal-yellow border-3 border-brutal-black px-2 py-1 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <span className="flex-1 font-mono text-xs font-bold truncate" title={vol}>{vol}</span>
                  <span className="text-[9px] font-bold uppercase bg-brutal-black text-white px-1.5 py-0.5 border-2 border-brutal-black">
                    {t('config.volumeMounts.globalBadge')}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Per-chat volumes (editable) */}
        <div className="space-y-2">
          <div className="text-[9px] font-bold uppercase text-brutal-black opacity-60">{t('config.volumeMounts.perChat')}</div>

          <div className="flex flex-col gap-2 p-2 border-2 border-brutal-black bg-neutral-50">
            <div className="flex flex-col gap-2 p-2 border-2 border-brutal-black bg-neutral-50">
              <div className="text-[10px] text-brutal-black opacity-60 italic">
                {t('config.volumeMounts.manageFromFolder')}
              </div>
            </div>
          </div>


          {(config.sandbox_volumes || []).length > 0 && (
            <ul className="space-y-1">
              {(config.sandbox_volumes || []).map((vol: string, idx: number) => (
                <li key={idx} className="flex items-center gap-2 bg-white border-3 border-brutal-black px-2 py-1 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <span className="flex-1 font-mono text-xs font-bold truncate" title={vol}>{vol}</span>
                  <button
                    type="button"
                    onClick={() => {
                      const current = config.sandbox_volumes || [];
                      update({ sandbox_volumes: current.filter((_: string, i: number) => i !== idx) });
                    }}
                    className="text-white bg-brutal-red border-2 border-brutal-black text-xs font-bold px-1.5 py-0.5 hover:bg-red-600 transition-colors"
                    title={t('common.remove')}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="block font-bold tracking-wide text-brutal-black uppercase">{t('config.mcp.label')}</label>
          <span className="text-[9px] font-bold uppercase text-neutral-500">{t('config.mcp.manageInSettings')}</span>
        </div>
        <div className="space-y-2">
          {servers.length === 0 && (
            <div className="text-[11px] text-brutal-black font-bold uppercase">
              <span>{t('config.mcp.noneConfiguredManageInSettings')}</span>
            </div>
          )}
          <ul
            className={`space-y-2 ${servers.length > 4 ? 'max-h-40 overflow-y-auto pr-1' : ''}`}
            style={servers.length > 4 ? { scrollbarGutter: 'stable both-edges' } : undefined}
          >
            {servers.map((s, idx) => (
              <li key={s.name} className="flex items-center gap-2 bg-white border-3 border-brutal-black px-2 py-1 group shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn transition-transform animate-brutal-drop" style={{ animationDelay: `${idx * 0.05}s` }}>
                <input aria-label={t('config.mcp.enableServer')} type="checkbox" checked={s.enabled} onChange={() => toggleServer(s.name)} disabled={loading} className="w-4 h-4 border-2 border-brutal-black accent-brutal-black" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="truncate font-bold text-brutal-black text-xs" title={s.name}>{s.name}</div>
                    <span className={`text-[10px] px-1.5 py-0.5 border-2 font-bold uppercase ${s.enabled ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 text-brutal-black'}`}>{s.enabled ? t('common.on') : t('common.off')}</span>
                  </div>
                  {s.type === 'url' ? (
                    <div className="truncate text-brutal-black text-[11px] font-mono font-bold opacity-50" title={s.url}>{s.url}</div>
                  ) : (
                    <div className="text-brutal-black text-[11px] break-all truncate max-w-full whitespace-pre-line font-mono font-bold opacity-50">
                      <span className="break-all truncate max-w-full" title={s.command}>{s.command}</span>
                      {s.args && s.args.length > 0 && (
                        <span> <span className="break-all truncate max-w-full" title={s.args.join(', ')}>[{s.args.join(', ')}]</span></span>
                      )}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {config.mcp_urls && (
            <div className="text-xs text-brutal-black font-mono font-bold">
              {t('config.mcp.enabledUrls', { count: Array.isArray(config.mcp_urls) ? config.mcp_urls.length : Object.keys(config.mcp_urls).length })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
