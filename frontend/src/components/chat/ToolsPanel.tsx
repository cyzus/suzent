import React, { useCallback, useEffect, useState } from 'react';
import { useChatCoreStore } from '../../hooks/useChatStore';
import { useActivatedToolsStore } from '../../hooks/useActivatedToolsStore';
import { deactivateTool, fetchMcpServers, setMcpServerEnabled } from '../../lib/api';
import { CapabilityToolPicker } from '../tools/CapabilityToolPicker';

type MCPServer = {
  name: string;
  type: 'url' | 'stdio';
  url?: string;
  command?: string;
  args?: string[];
  enabled: boolean;
};

export function ToolsPanel(): React.ReactElement | null {
  const { config, setConfig, backendConfig, currentChatId } = useChatCoreStore();
  const { activatedByAI, removeActivatedTool } = useActivatedToolsStore();
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [mcpLoading, setMcpLoading] = useState(false);

  useEffect(() => {
    fetchMcpServers().then(data => {
      const urls = data.urls || {};
      const stdio = data.stdio || {};
      const enabled = data.enabled || {};
      const urlServers: MCPServer[] = Object.entries(urls).map(([name, url]) => ({
        type: 'url', name, url: String(url), enabled: !!enabled[name],
      }));
      const stdioServers: MCPServer[] = Object.entries(stdio).map(([name, params]: [string, any]) => ({
        type: 'stdio', name, command: params.command, args: params.args, enabled: !!enabled[name],
      }));
      setServers([...urlServers, ...stdioServers]);
    }).catch(() => {});
  }, [backendConfig]);

  const update = useCallback((patch: Partial<typeof config>) => {
    setConfig(prev => ({ ...prev, ...patch }));
  }, [setConfig]);

  if (!backendConfig) return (
    <div className="flex items-center justify-center h-full text-neutral-400 text-xs">Loading…</div>
  );

  const rawTools = Array.isArray(backendConfig.tools) ? backendConfig.tools : [];
  const available: string[] = rawTools;
  const selected: string[] = config.tools || [];

  const toggleMcp = async (name: string) => {
    setMcpLoading(true);
    try {
      const server = servers.find(s => s.name === name);
      if (!server) return;
      await setMcpServerEnabled(name, !server.enabled);
      const updated = servers.map(s => s.name === name ? { ...s, enabled: !s.enabled } : s);
      setServers(updated);
      const mcp_enabled: Record<string, boolean> = {};
      const mcp_urls: Record<string, string> = {};
      for (const s of updated) {
        mcp_enabled[s.name] = s.enabled;
        if (s.enabled && s.type === 'url' && s.url) mcp_urls[s.name] = s.url;
      }
      update({ mcp_enabled, mcp_urls });
    } finally {
      setMcpLoading(false);
    }
  };

  if (available.length === 0) return (
    <div className="flex items-center justify-center h-full text-neutral-400 text-xs px-4 text-center">
      No tools configured
    </div>
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tools section */}
      <div className="px-3 pt-3 pb-1.5">
        <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400">Tools</span>
      </div>
      <div className="flex flex-col overflow-y-auto flex-1 scrollbar-thin">
        <CapabilityToolPicker
          backendConfig={backendConfig}
          selected={selected}
          activatedByAI={activatedByAI}
          onChange={tools => update({ tools })}
          onDeactivate={tool => {
            removeActivatedTool(tool);
            deactivateTool(currentChatId || '', tool);
          }}
          compact
        />

        {/* MCP Servers section */}
        {servers.length > 0 && (
          <>
            <div className="px-3 pt-3 pb-1.5 border-t border-brutal-black/10 dark:border-neutral-700 mt-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400">MCP Servers</span>
            </div>
            <div className="flex flex-col gap-1 px-1.5 pb-3">
              {servers.map(server => (
                <button
                  key={server.name}
                  type="button"
                  onClick={() => !mcpLoading && toggleMcp(server.name)}
                  disabled={mcpLoading}
                  className={`flex items-center gap-2.5 px-2.5 py-1.5 border-2 text-[10px] font-bold uppercase transition-all w-full text-left shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 ${
                    server.enabled
                      ? 'bg-brutal-green text-brutal-black border-brutal-black'
                      : 'border-brutal-black text-brutal-black dark:text-white bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700'
                  }`}
                >
                  <div className={`w-3.5 h-3.5 border-2 border-brutal-black flex-shrink-0 flex items-center justify-center ${server.enabled ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}>
                    {server.enabled && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                  </div>
                  <span className="truncate flex-1">{server.name}</span>
                  <span className={`text-[9px] px-1 py-0.5 border font-bold flex-shrink-0 ${server.enabled ? 'border-brutal-black bg-white text-brutal-black' : 'border-neutral-400 bg-neutral-100 dark:bg-zinc-700 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400'}`}>
                    MCP
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
