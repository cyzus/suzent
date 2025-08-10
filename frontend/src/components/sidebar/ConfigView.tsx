import React, { useEffect, useState } from 'react';
import { useChatStore } from '../../hooks/useChatStore';

interface MCPServer { id: string; name: string; url: string; enabled: boolean }

export const ConfigView: React.FC = () => {
  const { config, setConfig, backendConfig, resetChat } = useChatStore();
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [srvName, setSrvName] = useState('');
  const [srvUrl, setSrvUrl] = useState('');
  const LS_KEY = 'mcp_servers_v1';

  // Load from localStorage OR backend defaults once
  useEffect(() => {
    if (servers.length > 0) return; // already initialized
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) {
        const parsed: MCPServer[] = JSON.parse(raw);
        setServers(parsed);
        return;
      }
    } catch { /* ignore */ }
    // Fallback to config.mcp_urls (if backend supplied) or DEFAULT_MCP_URLS embedded in backend?
    if (config.mcp_urls && config.mcp_urls.length) {
      setServers(config.mcp_urls.map(u => ({ id: u, name: new URL(u).host || u, url: u, enabled: true })));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.mcp_urls]);

  // Persist to localStorage
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(servers)); } catch { /* ignore */ }
  }, [servers]);

  // Sync enabled server urls back to config
  useEffect(() => {
    const enabled = servers.filter(s => s.enabled).map(s => s.url);
    setConfig({ ...config, mcp_urls: enabled });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers]);

  if (!backendConfig) {
    return <div className="text-xs text-neutral-500">Loading config...</div>;
  }

  const update = (patch: Partial<typeof config>) => setConfig({ ...config, ...patch });

  const toggleTool = (tool: string) => {
    const tools = config.tools.includes(tool) ? config.tools.filter((t: string) => t !== tool) : [...config.tools, tool];
    update({ tools });
  };

  const addServer = () => {
    if (!srvUrl.trim()) return;
    try { new URL(srvUrl); } catch { return; }
    setServers(prev => [...prev, { id: crypto.randomUUID(), name: srvName.trim() || new URL(srvUrl).host, url: srvUrl.trim(), enabled: true }]);
    setSrvName(''); setSrvUrl('');
  };
  const toggleServer = (id: string) => setServers(prev => prev.map(s => s.id === id ? { ...s, enabled: !s.enabled } : s));
  const removeServer = (id: string) => setServers(prev => prev.filter(s => s.id !== id));

  return (
    <div className="space-y-6 text-xs">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold tracking-wide text-neutral-700">Session</div>
        <button type="button" onClick={resetChat} className="text-[11px] px-2 py-1 rounded bg-neutral-200 hover:bg-neutral-300 text-neutral-700">New Chat</button>
      </div>
      <div className="space-y-1">
        <label className="block font-medium tracking-wide text-neutral-700">Model</label>
        <select
          value={config.model}
          onChange={e => update({ model: e.target.value })}
          className="w-full bg-white/70 border border-neutral-300 rounded-lg px-3 py-2 focus:border-brand-500 focus:outline-none"
        >
          {backendConfig.models.map((m: string) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="space-y-1">
        <label className="block font-medium tracking-wide text-neutral-700">Agent</label>
        <select
          value={config.agent}
          onChange={e => update({ agent: e.target.value })}
          className="w-full bg-white/70 border border-neutral-300 rounded-lg px-3 py-2 focus:border-brand-500 focus:outline-none"
        >
          {backendConfig.agents.map((a: string) => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <div className="space-y-2">
        <label className="block font-medium tracking-wide text-neutral-700">Tools</label>
        <div className="flex flex-wrap gap-2">
          {backendConfig.tools.map((tool: string) => {
            const active = config.tools.includes(tool);
            return (
              <button
                key={tool}
                type="button"
                onClick={() => toggleTool(tool)}
                className={`px-2.5 py-1 rounded-full border text-[11px] font-medium transition-colors ${active ? 'bg-brand-600 text-white border-brand-500 shadow' : 'border-neutral-300 text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 bg-white/70'}`}
              >
                {tool}
              </button>
            );
          })}
        </div>
      </div>
      <div className="space-y-2">
        <label className="block font-medium tracking-wide text-neutral-700">MCP Servers</label>
        <div className="space-y-2">
          <div className="flex gap-2 flex-wrap items-start">
            <input
              value={srvName}
              onChange={e => setSrvName(e.target.value)}
              placeholder="Name"
              className="w-28 shrink-0 bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
            />
            <input
              value={srvUrl}
              onChange={e => setSrvUrl(e.target.value)}
              placeholder="https://host/path"
              className="flex-1 min-w-[140px] bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
            />
            <button type="button" onClick={addServer} className="shrink-0 px-3 py-1 rounded bg-brand-600 text-white text-[11px] hover:bg-brand-500 disabled:opacity-50" disabled={!srvUrl}>Add</button>
          </div>
          {servers.length === 0 && (
            <div className="text-[11px] text-neutral-400 flex items-center gap-1">
              <span>No MCP servers configured.</span>
            </div>
          )}
          <ul className="space-y-1 max-h-40 overflow-y-auto pr-1">
            {servers.map(s => (
              <li key={s.id} className="flex items-center gap-2 bg-white/80 border border-neutral-200 rounded px-2 py-1 group">
                <input aria-label="Enable server" type="checkbox" checked={s.enabled} onChange={() => toggleServer(s.id)} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="truncate font-medium text-neutral-700" title={s.name}>{s.name}</div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${s.enabled ? 'border-green-300 text-green-600 bg-green-50' : 'border-neutral-300 text-neutral-400 bg-neutral-50'}`}>{s.enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                  <div className="truncate text-neutral-400 text-[11px]" title={s.url}>{s.url}</div>
                </div>
                <button type="button" onClick={() => removeServer(s.id)} className="text-neutral-400 hover:text-red-500 text-xs" title="Remove">✕</button>
              </li>
            ))}
          </ul>
          {config.mcp_urls && config.mcp_urls.length > 0 && (
            <div className="text-[10px] text-neutral-400">Enabled: {config.mcp_urls.length} URL(s)</div>
          )}
        </div>
      </div>
    </div>
  );
};
