
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
    return <div className="text-xs text-brutal-black font-bold uppercase animate-brutal-blink">Loading config...</div>;
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
        <div className="text-sm font-brutal tracking-wide text-brutal-black uppercase">Session</div>
        <button type="button" onClick={resetChat} className="text-xs px-2 py-1 bg-brutal-blue border-2 border-brutal-black shadow-brutal-sm hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-none transition-transform duration-75 text-white font-bold uppercase">New Chat</button>
      </div>
      <div className="space-y-1">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">Model</label>
        <select
          value={config.model}
          onChange={e => update({ model: e.target.value })}
          className="w-full bg-brutal-white border-3 border-brutal-black px-3 py-2 font-bold text-sm focus:shadow-brutal-sm focus:outline-none"
        >
          {backendConfig.models.map((m: string) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="space-y-1">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">Agent</label>
        <select
          value={config.agent}
          onChange={e => update({ agent: e.target.value })}
          className="w-full bg-brutal-white border-3 border-brutal-black px-3 py-2 font-bold text-sm focus:shadow-brutal-sm focus:outline-none"
        >
          {backendConfig.agents.map((a: string) => <option key={a} value={a}>{a}</option>)}
        </select>
        <div className="text-xs text-brutal-black mt-1 leading-relaxed font-medium">
          {config.agent === 'CodeAgent' && (
            <span>📝 Writes and executes Python code</span>
          )}
          {config.agent === 'ToolcallingAgent' && (
            <span>🔧 Direct tool calling without code</span>
          )}
        </div>
      </div>
      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">Tools</label>
        <div className="flex flex-wrap gap-2">
          {backendConfig.tools.map((tool: string) => {
            const active = (config.tools || []).includes(tool);
            return (
              <button
                key={tool}
                type="button"
                onClick={() => toggleTool(tool)}
                className={`px-2.5 py-1 border-2 text-xs font-bold uppercase ${
                  active
                    ? 'bg-brutal-green text-brutal-black border-brutal-black shadow-brutal-sm'
                    : 'border-brutal-black text-brutal-black hover:shadow-brutal-sm bg-brutal-white'
                }`}
              >
                {tool}
              </button>
            );
          })}
        </div>
      </div>
      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black uppercase">MCP Servers</label>
        <div className="space-y-2">
          <div className="flex gap-2 flex-wrap items-start">
            <select value={addType} onChange={e => setAddType(e.target.value as 'url' | 'stdio')} className="w-20 bg-brutal-white border-2 border-brutal-black px-2 py-1 font-bold text-xs focus:outline-none focus:shadow-brutal-sm">
              <option value="url">URL</option>
              <option value="stdio">Stdio</option>
            </select>
            <input
              value={srvName}
              onChange={e => setSrvName(e.target.value)}
              placeholder="Name"
              className="w-28 shrink-0 bg-brutal-white border-2 border-brutal-black px-2 py-1 font-mono font-bold text-xs placeholder:opacity-40 focus:outline-none focus:shadow-brutal-sm"
            />
            {addType === 'url' ? (
              <input
                value={srvUrl}
                onChange={e => setSrvUrl(e.target.value)}
                placeholder="https://host/path"
                className="flex-1 min-w-[140px] bg-brutal-white border-2 border-brutal-black px-2 py-1 font-mono font-bold text-xs placeholder:opacity-40 focus:outline-none focus:shadow-brutal-sm"
              />
            ) : (
              <>
                <input
                  value={stdioCmd}
                  onChange={e => setStdioCmd(e.target.value)}
                  placeholder="command"
                  className="w-36 bg-brutal-white border-2 border-brutal-black px-2 py-1 font-mono font-bold text-xs placeholder:opacity-40 focus:outline-none focus:shadow-brutal-sm"
                />
                <input
                  value={stdioArgs}
                  onChange={e => setStdioArgs(e.target.value)}
                  placeholder="args"
                  className="w-36 bg-brutal-white border-2 border-brutal-black px-2 py-1 font-mono font-bold text-xs placeholder:opacity-40 focus:outline-none focus:shadow-brutal-sm"
                />
                <input
                  value={stdioEnv}
                  onChange={e => setStdioEnv(e.target.value)}
                  placeholder="env"
                  className="w-36 bg-brutal-white border-2 border-brutal-black px-2 py-1 font-mono font-bold text-xs placeholder:opacity-40 focus:outline-none focus:shadow-brutal-sm"
                />
              </>
            )}
            <button type="button" onClick={addServer} className="shrink-0 px-3 py-1 bg-brutal-green border-2 border-brutal-black text-brutal-black text-xs font-bold uppercase hover:shadow-brutal-sm disabled:opacity-50" disabled={addType === 'url' ? !srvUrl : !stdioCmd}>Add</button>
          </div>
          {servers.length === 0 && (
            <div className="text-[11px] text-brutal-black font-bold uppercase">
              <span>No MCP servers configured.</span>
            </div>
          )}
          <ul
            className={`space-y-1 ${servers.length > 4 ? 'max-h-40 overflow-y-auto pr-1' : ''}`}
            style={servers.length > 4 ? { scrollbarGutter: 'stable both-edges' } : undefined}
          >
            {servers.map(s => (
              <li key={s.name} className="flex items-center gap-2 bg-brutal-white border-3 border-brutal-black px-2 py-1 group">
                <input aria-label="Enable server" type="checkbox" checked={s.enabled} onChange={() => toggleServer(s.name)} disabled={loading} className="w-4 h-4 border-2 border-brutal-black" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="truncate font-bold text-brutal-black text-xs" title={s.name}>{s.name}</div>
                    <span className={`text-[10px] px-1.5 py-0.5 border-2 font-bold uppercase ${s.enabled ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 text-brutal-black'}`}>{s.enabled ? 'ON' : 'OFF'}</span>
                  </div>
                  {s.type === 'url' ? (
                    <div className="truncate text-brutal-black text-[11px] font-mono font-bold opacity-50" title={s.url}>{s.url}</div>
                  ) : (
                    <div className="text-brutal-black text-[11px] break-all truncate max-w-full whitespace-pre-line font-mono font-bold opacity-50">
                      <span className="break-all truncate max-w-full" title={s.command}>{s.command}</span>
                      {s.args && s.args.length > 0 && (
                        <span> <span className="break-all truncate max-w-full" title={s.args.join(', ')}>[{s.args.join(', ')}]</span></span>
                      )}
                      {s.env && Object.keys(s.env).length > 0 && (
                        <span> <span className="break-all truncate max-w-full" title={JSON.stringify(s.env)}>env:{JSON.stringify(s.env)}</span></span>
                      )}
                    </div>
                  )}
                </div>
                <button type="button" onClick={() => removeServer(s.name)} className="text-brutal-white bg-brutal-red border-2 border-brutal-black hover:shadow-brutal-sm text-xs font-bold px-1" title="Remove" disabled={loading}>×</button>
              </li>
            ))}
          </ul>
          {config.mcp_urls && config.mcp_urls.length > 0 && (
            <div className="text-xs text-brutal-black font-mono font-bold">ENABLED: {config.mcp_urls.length} URL(S)</div>
          )}
        </div>
      </div>
    </div>
  );
};
