
import React, { useEffect, useState, useCallback } from 'react';
import { flushSync } from 'react-dom';
import { useChatStore } from '../../hooks/useChatStore';
import { fetchMcpServers, addMcpServer, removeMcpServer, setMcpServerEnabled } from '../../lib/api';

type MCPServer =
  | { type: 'url'; name: string; url: string; enabled: boolean }
  | { type: 'stdio'; name: string; command: string; args?: string[]; env?: Record<string, string>; enabled: boolean };

export const ConfigView: React.FC = () => {
  const { config, setConfig, backendConfig, resetChat } = useChatStore();

  const [servers, setServers] = useState<MCPServer[]>([]);
  const [srvName, setSrvName] = useState('');
  const [srvUrl, setSrvUrl] = useState('');
  const [stdioCmd, setStdioCmd] = useState('');
  const [stdioArgs, setStdioArgs] = useState('');
  const [stdioEnv, setStdioEnv] = useState('');
  const [addType, setAddType] = useState<'url' | 'stdio'>('url');
  const [loading, setLoading] = useState(false);

  // Load from backend
  useEffect(() => {
    fetchMcpServers().then(data => {
      const urls = data.urls || {};
      const stdio = data.stdio || {};
      const enabled = data.enabled || {};
      const urlServers: MCPServer[] = Object.entries(urls).map(([name, url]: [string, unknown]) => ({ type: 'url', name, url: String(url), enabled: !!enabled[name] }));
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
  }, []);

  // Sync enabled server urls and enabled state for all servers back to config
  useEffect(() => {
    const enabledUrls = servers.filter(s => s.enabled && s.type === 'url').map(s => (s as any).url);
    // mcp_enabled: { [name]: boolean }
    const mcp_enabled: Record<string, boolean> = {};
    servers.forEach(s => { mcp_enabled[s.name] = s.enabled; });
    setConfig(prevConfig => ({ ...prevConfig, mcp_urls: enabledUrls, mcp_enabled }));
  }, [servers, setConfig]);

  if (!backendConfig) {
    return <div className="text-xs text-neutral-500">Loading config...</div>;
  }

  const update = useCallback((patch: Partial<typeof config>) => {
    setConfig(prevConfig => ({ ...prevConfig, ...patch }));
  }, [setConfig]);

  const toggleTool = (tool: string) => {
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
  };


  const addServer = useCallback(async () => {
    setLoading(true);
    try {
      if (addType === 'url') {
        if (!srvUrl.trim()) return;
        try { new URL(srvUrl); } catch { return; }
        await addMcpServer(srvName.trim() || new URL(srvUrl).host, srvUrl.trim());
      } else {
        if (!stdioCmd.trim()) return;
        const args = stdioArgs.trim() ? stdioArgs.split(',').map(s => s.trim()).filter(Boolean) : undefined;
        let env: Record<string, string> | undefined = undefined;
        if (stdioEnv.trim()) {
          env = {};
          stdioEnv.split(',').forEach(pair => {
            const [k, v] = pair.split('=').map(s => s.trim());
            if (k && v && env) env[k] = v;
          });
        }
        await addMcpServer(srvName.trim() || stdioCmd.trim(), undefined, { command: stdioCmd.trim(), args, env });
      }
      setSrvName(''); setSrvUrl(''); setStdioCmd(''); setStdioArgs(''); setStdioEnv('');
      const data = await fetchMcpServers();
      const urls = data.urls || {};
      const stdio = data.stdio || {};
      const enabled = data.enabled || {};
      const urlServers: MCPServer[] = Object.entries(urls).map(([name, url]: [string, unknown]) => ({ type: 'url', name, url: String(url), enabled: !!enabled[name] }));
      const stdioServers: MCPServer[] = Object.entries(stdio).map(([name, params]: [string, any]) => ({
        type: 'stdio',
        name,
        command: params.command,
        args: params.args,
        env: params.env,
        enabled: !!enabled[name],
      }));
      setServers([...urlServers, ...stdioServers]);
    } finally {
      setLoading(false);
    }
  }, [addType, srvName, srvUrl, stdioCmd, stdioArgs, stdioEnv]);

  const toggleServer = useCallback(async (name: string) => {
    setLoading(true);
    try {
      const server = servers.find(s => s.name === name);
      if (!server) return;
      await setMcpServerEnabled(name, !server.enabled);
      setServers(prev => prev.map(s => s.name === name ? { ...s, enabled: !s.enabled } : s));
    } finally {
      setLoading(false);
    }
  }, [servers]);

  const removeServer = useCallback(async (name: string) => {
    setLoading(true);
    try {
      await removeMcpServer(name);
      setServers(prev => prev.filter(s => s.name !== name));
    } finally {
      setLoading(false);
    }
  }, []);

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
        <div className="text-[10px] text-neutral-500 mt-1 leading-relaxed">
          {config.agent === 'CodeAgent' && (
            <span>📝 Writes and executes Python code for problem-solving</span>
          )}
          {config.agent === 'ToolcallingAgent' && (
            <span>🔧 Direct tool calling without code execution</span>
          )}
        </div>
      </div>
      <div className="space-y-2">
        <label className="block font-medium tracking-wide text-neutral-700">Tools</label>
        <div className="flex flex-wrap gap-2">
          {backendConfig.tools.map((tool: string) => {
            const active = (config.tools || []).includes(tool);
            return (
              <button
                key={tool}
                type="button"
                onClick={() => toggleTool(tool)}
                className={`px-2.5 py-1 rounded-full border text-[11px] font-medium transition-colors ${
                  active 
                    ? 'bg-brand-600 text-white border-brand-500 shadow' 
                    : 'border-neutral-300 text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 bg-white/70'
                }`}
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
            <select value={addType} onChange={e => setAddType(e.target.value as 'url' | 'stdio')} className="w-20 bg-white/70 border border-neutral-300 rounded px-2 py-1">
              <option value="url">URL</option>
              <option value="stdio">Stdio</option>
            </select>
            <input
              value={srvName}
              onChange={e => setSrvName(e.target.value)}
              placeholder="Name"
              className="w-28 shrink-0 bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
            />
            {addType === 'url' ? (
              <input
                value={srvUrl}
                onChange={e => setSrvUrl(e.target.value)}
                placeholder="https://host/path"
                className="flex-1 min-w-[140px] bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
              />
            ) : (
              <>
                <input
                  value={stdioCmd}
                  onChange={e => setStdioCmd(e.target.value)}
                  placeholder="Command (e.g. mcp-obsidian)"
                  className="w-36 bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
                />
                <input
                  value={stdioArgs}
                  onChange={e => setStdioArgs(e.target.value)}
                  placeholder="Args (comma separated)"
                  className="w-36 bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
                />
                <input
                  value={stdioEnv}
                  onChange={e => setStdioEnv(e.target.value)}
                  placeholder="Env (KEY=VAL,...)"
                  className="w-36 bg-white/70 border border-neutral-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
                />
              </>
            )}
            <button type="button" onClick={addServer} className="shrink-0 px-3 py-1 rounded bg-brand-600 text-white text-[11px] hover:bg-brand-500 disabled:opacity-50" disabled={addType === 'url' ? !srvUrl : !stdioCmd}>Add</button>
          </div>
          {servers.length === 0 && (
            <div className="text-[11px] text-neutral-400 flex items-center gap-1">
              <span>No MCP servers configured.</span>
            </div>
          )}
          <ul
            className={`space-y-1 ${servers.length > 4 ? 'max-h-40 overflow-y-auto pr-1' : ''}`}
            style={servers.length > 4 ? { scrollbarGutter: 'stable both-edges' } : undefined}
          >
            {servers.map(s => (
              <li key={s.name} className="flex items-center gap-2 bg-white/80 border border-neutral-200 rounded px-2 py-1 group">
                <input aria-label="Enable server" type="checkbox" checked={s.enabled} onChange={() => toggleServer(s.name)} disabled={loading} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="truncate font-medium text-neutral-700" title={s.name}>{s.name}</div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${s.enabled ? 'border-green-300 text-green-600 bg-green-50' : 'border-neutral-300 text-neutral-400 bg-neutral-50'}`}>{s.enabled ? 'Enabled' : 'Disabled'}</span>
                  </div>
                  {s.type === 'url' ? (
                    <div className="truncate text-neutral-400 text-[11px]" title={s.url}>{s.url}</div>
                  ) : (
                    <div className="text-neutral-400 text-[11px] break-all truncate max-w-full whitespace-pre-line">
                      <span className="font-mono break-all truncate max-w-full" title={s.command}>{s.command}</span>
                      {s.args && s.args.length > 0 && (
                        <span> <span className="font-mono break-all truncate max-w-full" title={s.args.join(', ')}>[{s.args.join(', ')}]</span></span>
                      )}
                      {s.env && Object.keys(s.env).length > 0 && (
                        <span> <span className="font-mono break-all truncate max-w-full" title={JSON.stringify(s.env)}>env:{JSON.stringify(s.env)}</span></span>
                      )}
                    </div>
                  )}
                </div>
                <button type="button" onClick={() => removeServer(s.name)} className="text-neutral-400 hover:text-red-500 text-xs" title="Remove" disabled={loading}>✕</button>
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
