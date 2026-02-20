import React, { useEffect, useState } from 'react';
import { useChatStore } from '../hooks/useChatStore';
import { useI18n } from '../i18n';

interface MCPServer { name: string; url: string; enabled: boolean }

const STORAGE_KEY = 'suzent_mcp_servers';

export const MCPServers: React.FC = () => {
  const { t } = useI18n();
  const { config, setConfig } = useChatStore();
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');

  // Load persisted servers from localStorage on mount. If none, derive from config.mcp_urls
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed: MCPServer[] = JSON.parse(raw);
        setServers(parsed);
        return;
      }
    } catch (e) {
      console.warn('Failed to load MCP servers from localStorage', e);
    }

    // Fallback: if config has mcp_urls, populate servers list with empty names
    if (config && config.mcp_urls && config.mcp_urls.length) {
      setServers(config.mcp_urls.map(u => ({ name: '', url: u, enabled: true })));
    }
  }, []); // run once

  // Whenever servers change, persist to localStorage and sync enabled URLs into chat config
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
    } catch (e) {
      console.warn('Failed to save MCP servers to localStorage', e);
    }

    const enabledUrls = servers.filter(s => s.enabled).map(s => s.url);
    // Only update config if it changed to avoid noisy saves
    const prev = config.mcp_urls ?? [];
    const equal = prev.length === enabledUrls.length && prev.every((v, i) => v === enabledUrls[i]);
    if (!equal) {
      setConfig(prevConfig => ({ ...prevConfig, mcp_urls: enabledUrls }));
    }
  }, [servers, config, setConfig]);

  const add = () => {
    if (!name || !url) return;
    setServers(prev => [...prev, { name, url, enabled: true }]);
    setName(''); setUrl('');
  };

  const toggle = (i: number) => setServers(prev => prev.map((s, idx) => idx === i ? { ...s, enabled: !s.enabled } : s));
  const remove = (i: number) => setServers(prev => prev.filter((_, idx) => idx !== i));

  // If the global config changes externally (e.g., loading a chat), reflect enabled state
  useEffect(() => {
    if (!config) return;
    const urls = new Set(config.mcp_urls ?? []);
    setServers(prev => {
      // Keep existing servers, but update enabled flags based on config
      const updated = prev.map(s => ({ ...s, enabled: urls.has(s.url) }));
      // Add any urls from config that are missing locally
      (config.mcp_urls ?? []).forEach(u => {
        if (!updated.find(s => s.url === u)) {
          updated.push({ name: '', url: u, enabled: true });
        }
      });
      return updated;
    });
  }, [config && JSON.stringify(config.mcp_urls)]);

  return (
    <div className="space-y-3 text-xs">
      <div className="font-medium">{t('config.mcp.label')}</div>
      <div className="flex gap-2">
        <input value={name} onChange={e => setName(e.target.value)} placeholder={t('config.mcp.name')} className="flex-1 bg-neutral-800 border border-neutral-700 rounded px-2 py-1" />
        <input value={url} onChange={e => setUrl(e.target.value)} placeholder={t('config.mcp.url')} className="flex-[2] bg-neutral-800 border border-neutral-700 rounded px-2 py-1" />
        <button onClick={add} className="bg-brand-600 px-2 rounded">{t('common.add')}</button>
      </div>
      <ul className="space-y-2">
        {servers.map((s, i) => (
          <li key={i} className="flex items-center gap-2 bg-neutral-800 rounded p-2">
            <input type="checkbox" checked={s.enabled} onChange={() => toggle(i)} />
            <div className="flex-1">
              <div className="font-semibold">{s.name || s.url}</div>
              {s.name ? <div className="text-neutral-400">{s.url}</div> : null}
            </div>
            <button onClick={() => remove(i)} className="text-neutral-400 hover:text-red-400">✕</button>
          </li>
        ))}
      </ul>
    </div>
  );
};
