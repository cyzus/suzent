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

    // Fallback: if config has mcp_urls, populate servers list
    const mcpUrls = config?.mcp_urls;
    if (mcpUrls) {
      if (Array.isArray(mcpUrls) && mcpUrls.length > 0) {
        setServers(mcpUrls.map(u => ({ name: '', url: u, enabled: true })));
      } else if (!Array.isArray(mcpUrls) && Object.keys(mcpUrls).length > 0) {
        setServers(Object.entries(mcpUrls).map(([n, u]) => ({ name: n, url: u, enabled: true })));
      }
    }
  }, []); // run once

  // Whenever servers change, persist to localStorage and sync enabled URLs into chat config
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
    } catch (e) {
      console.warn('Failed to save MCP servers to localStorage', e);
    }

    // Generate dictionary { [name]: url } for enabled servers
    const enabledUrlDict: Record<string, string> = {};
    servers.forEach(s => {
      if (s.enabled) {
        // Fallback to URL as name if name is missing (legacy)
        enabledUrlDict[s.name || s.url] = s.url;
      }
    });

    // Only update config if it changed
    const prev = config.mcp_urls;
    let changed = false;

    if (!prev) {
      changed = Object.keys(enabledUrlDict).length > 0;
    } else if (Array.isArray(prev)) {
      // Changed if we now support dictionary or if lengths differ (simplification: just switch to dict)
      changed = true;
    } else {
      // Compare dicts
      const prevKeys = Object.keys(prev).sort();
      const newKeys = Object.keys(enabledUrlDict).sort();
      if (prevKeys.length !== newKeys.length || !prevKeys.every((k, i) => k === newKeys[i] && prev[k] === enabledUrlDict[k])) {
        changed = true;
      }
    }

    if (changed) {
      setConfig(prevConfig => ({ ...prevConfig, mcp_urls: enabledUrlDict }));
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
    const mcpUrls = config.mcp_urls;

    // Normalize to set of URLs for checking existence
    const configUrlSet = new Set<string>();
    const configEntries: { name: string, url: string }[] = [];

    if (Array.isArray(mcpUrls)) {
      mcpUrls.forEach(u => {
        configUrlSet.add(u);
        configEntries.push({ name: '', url: u });
      });
    } else if (mcpUrls) {
      Object.entries(mcpUrls).forEach(([n, u]) => {
        configUrlSet.add(u);
        configEntries.push({ name: n, url: u });
      });
    }

    setServers(prev => {
      // Keep existing servers, but update enabled flags based on config
      const updated = prev.map(s => ({ ...s, enabled: configUrlSet.has(s.url) }));

      // Add any urls from config that are missing locally
      configEntries.forEach(entry => {
        if (!updated.find(s => s.url === entry.url)) {
          updated.push({ name: entry.name, url: entry.url, enabled: true });
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
