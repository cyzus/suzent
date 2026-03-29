import React, { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

import { useChatCoreStore, useChatStreamingStore } from '../../hooks/useChatStore';
import { fetchMcpServers, setMcpServerEnabled } from '../../lib/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalSelect } from '../BrutalSelect';
import { useI18n } from '../../i18n';


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

interface ConfigViewProps {
  isActive?: boolean;
}

export function ConfigView({ isActive = true }: ConfigViewProps): React.ReactElement {
  const { config, setConfig, backendConfig, currentChatId, loadChat } = useChatCoreStore();
  const { isStreaming } = useChatStreamingStore();
  const { t } = useI18n();

  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [liveLastRunAt, setLiveLastRunAt] = useState<string | null>(null);
  const [liveLastError, setLiveLastError] = useState<string | null>(null);
  const [isEditingMd, setIsEditingMd] = useState(false);
  const [mdDraft, setMdDraft] = useState('');

  const prevMcpStateRef = useRef<string>('');

  // Keep stable refs to avoid re-running the poll effect when these change
  const setConfigRef = useRef(setConfig);
  const loadChatRef = useRef(loadChat);
  const lastResultRef = useRef<string | null>(null);
  const isEditingInstructionsRef = useRef(false); // don't overwrite mid-edit
  const isStreamingRef = useRef(isStreaming);
  const heartbeatDispatchedRef = useRef(false); // prevent double-dispatch per due cycle
  const configRef = useRef(config);
  useEffect(() => { setConfigRef.current = setConfig; }, [setConfig]);
  useEffect(() => { loadChatRef.current = loadChat; }, [loadChat]);
  useEffect(() => { isStreamingRef.current = isStreaming; }, [isStreaming]);
  useEffect(() => { configRef.current = config; }, [config]);

  // Poll live heartbeat status every 10 s — always active for the current chat.
  // This syncs state from external changes (CLI, another session) back to the UI,
  // and refreshes chat messages when a new non-OK heartbeat result is detected.
  useEffect(() => {
    if (!currentChatId || !isActive) return;
    lastResultRef.current = null; // reset on chat switch
    heartbeatDispatchedRef.current = false;
    let cancelled = false;
    const poll = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      try {
        const { fetchHeartbeatStatus } = await import('../../lib/api');
        const status = await fetchHeartbeatStatus(currentChatId);
        if (!cancelled) {
          setLiveLastRunAt(status.last_run_at ?? null);
          setLiveLastError(status.last_error ?? null);
          // Sync enabled/interval/instructions back — bail out early if unchanged
          setConfigRef.current(prev => {
            const sameEnabled = prev.heartbeat_enabled === status.enabled;
            const sameInterval = status.interval_minutes == null || prev.heartbeat_interval_minutes === status.interval_minutes;
            const sameInstructions = isEditingInstructionsRef.current ||
              status.heartbeat_instructions == null ||
              prev.heartbeat_instructions === status.heartbeat_instructions;
            if (sameEnabled && sameInterval && sameInstructions) return prev;
            return {
              ...prev,
              heartbeat_enabled: status.enabled,
              ...(status.interval_minutes != null ? { heartbeat_interval_minutes: status.interval_minutes } : {}),
              ...(!isEditingInstructionsRef.current && status.heartbeat_instructions != null
                ? { heartbeat_instructions: status.heartbeat_instructions } : {}),
            };
          });
          // If there's a new non-OK result we haven't seen yet, refresh the chat messages
          const newResult = status.last_result;
          if (newResult && newResult !== 'HEARTBEAT_OK' && newResult !== lastResultRef.current) {
            lastResultRef.current = newResult;
            loadChatRef.current(currentChatId);
          }

          // If the backend signals a heartbeat is due, initiate the SSE stream from the frontend
          // so the user sees streaming in the chat window.
          if (status.heartbeat_due && !isStreamingRef.current && !heartbeatDispatchedRef.current) {
            heartbeatDispatchedRef.current = true;
            window.dispatchEvent(new CustomEvent('agui:send-message', {
              detail: {
                body: { message: '', chat_id: currentChatId, is_heartbeat: true },
              },
            }));
          }
          // Reset dispatch flag when heartbeat is no longer due
          if (!status.heartbeat_due) {
            heartbeatDispatchedRef.current = false;
          }
        }
      } catch { /* silently ignore poll errors */ }
    };
    poll();
    const id = setInterval(poll, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [currentChatId, isActive]); // refs are intentionally omitted — updated via their own effects above

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
    return <div className="text-xs text-brutal-black dark:text-white font-bold uppercase animate-brutal-blink">{t('config.loading')}</div>;
  }

  return (
    <div className="space-y-6 text-xs">

      <div className="space-y-1">
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase">{t('config.agentLabel')}</label>
        <BrutalSelect
          value={config.agent}
          onChange={val => update({ agent: val })}
          options={backendConfig.agents}
        />
        <div className="text-xs text-brutal-black dark:text-neutral-400 mt-1 leading-relaxed font-medium">
          {config.agent === 'CodeAgent' && (
            <span>{t('config.agent.code')}</span>
          )}
          {config.agent === 'ToolcallingAgent' && (
            <span>{t('config.agent.toolcalling')}</span>
          )}
        </div>
      </div>
      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase">{t('config.toolsLabel')}</label>
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
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase">{t('config.memory.label')}</label>
        <button
          type="button"
          onClick={() => update({ memory_enabled: !config.memory_enabled })}
          className={`w-full px-3 py-2 border-3 text-xs font-bold uppercase transition-all duration-200 flex items-center justify-between ${config.memory_enabled
            ? 'bg-brutal-green text-brutal-black border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            : 'border-brutal-black text-brutal-black dark:text-white bg-white dark:bg-zinc-800 hover:bg-brutal-yellow dark:hover:bg-zinc-700 hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            }`}
        >
          <span>{t('config.memory.button')}</span>
          <span className={`text-[10px] px-2 py-1 border-2 font-bold ${config.memory_enabled
            ? 'border-brutal-black bg-white text-brutal-black'
            : 'border-brutal-black bg-neutral-200 dark:bg-zinc-600 text-brutal-black dark:text-white'
            }`}>
            {config.memory_enabled ? t('common.enabled') : t('common.disabled')}
          </span>
        </button>
        <div className="text-[11px] text-brutal-black dark:text-neutral-400 font-medium leading-relaxed">
          {config.memory_enabled ? (
            <span>{t('config.memory.enabledDesc')}</span>
          ) : (
            <span>{t('config.memory.disabledDesc')}</span>
          )}
        </div>
      </div>



      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase">{t('config.sandbox.label')}</label>
        <button
          type="button"
          onClick={() => update({ sandbox_enabled: !config.sandbox_enabled })}
          className={`w-full px-3 py-2 border-3 text-xs font-bold uppercase transition-all duration-200 flex items-center justify-between ${config.sandbox_enabled
            ? 'bg-brutal-green text-brutal-black border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            : 'border-brutal-black text-brutal-black dark:text-white bg-white dark:bg-zinc-800 hover:bg-brutal-yellow dark:hover:bg-zinc-700 hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            }`}
        >
          <span>{t('config.sandbox.button')}</span>
          <span className={`text-[10px] px-2 py-1 border-2 font-bold ${config.sandbox_enabled
            ? 'border-brutal-black bg-white text-brutal-black'
            : 'border-brutal-black bg-neutral-200 dark:bg-zinc-600 text-brutal-black dark:text-white'
            }`}>
            {config.sandbox_enabled ? t('common.enabled') : t('common.disabled')}
          </span>
        </button>
        <div className="text-[11px] text-brutal-black dark:text-neutral-400 font-medium leading-relaxed">
          {config.sandbox_enabled ? (
            <span>{t('config.sandbox.enabledDesc')}</span>
          ) : (
            <span>{t('config.sandbox.disabledDesc')}</span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase">Session Heartbeat</label>
        <button
          type="button"
          onClick={async () => {
            const newEnabled = !config.heartbeat_enabled;
            update({ heartbeat_enabled: newEnabled });
            try {
              if (newEnabled) {
                const { enableHeartbeat } = await import('../../lib/api');
                await enableHeartbeat(currentChatId || undefined);
              } else {
                const { disableHeartbeat } = await import('../../lib/api');
                await disableHeartbeat(currentChatId || undefined);
              }
            } catch (e: any) {
              // Roll back the optimistic update if the API call fails
              update({ heartbeat_enabled: !newEnabled });
              alert(e.message);
            }
          }}
          className={`w-full px-3 py-2 border-3 text-xs font-bold uppercase transition-all duration-200 flex items-center justify-between ${config.heartbeat_enabled
            ? 'bg-brutal-green text-brutal-black border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            : 'border-brutal-black text-brutal-black dark:text-white bg-white dark:bg-zinc-800 hover:bg-brutal-yellow dark:hover:bg-zinc-700 hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
            }`}
        >
          <span>Heartbeat</span>
          <span className={`text-[10px] px-2 py-1 border-2 font-bold ${config.heartbeat_enabled
            ? 'border-brutal-black bg-white text-brutal-black'
            : 'border-brutal-black bg-neutral-200 dark:bg-zinc-600 text-brutal-black dark:text-white'
            }`}>
            {config.heartbeat_enabled ? t('common.enabled') : t('common.disabled')}
          </span>
        </button>
        {config.heartbeat_enabled && (
          <div className="space-y-2 mt-2 p-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold uppercase text-neutral-600 dark:text-neutral-400">Interval (minutes)</label>
              <input
                type="number"
                min={1}
                value={config.heartbeat_interval_minutes || 30}
                onChange={e => update({ heartbeat_interval_minutes: parseInt(e.target.value, 10) || 30 })}
                onBlur={async e => {
                  const mins = parseInt(e.target.value, 10) || 30;
                  try {
                    const { setHeartbeatInterval } = await import('../../lib/api');
                    await setHeartbeatInterval(mins, currentChatId || undefined);
                  } catch { /* best-effort */ }
                }}
                className="w-24 bg-white dark:bg-zinc-800 border-2 border-brutal-black px-2 py-1 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-700 dark:text-white"
              />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-bold uppercase text-neutral-600 dark:text-neutral-400">heartbeat.md</label>
                {!isEditingMd ? (
                  <button
                    type="button"
                    onClick={() => { setMdDraft(config.heartbeat_instructions || ''); setIsEditingMd(true); isEditingInstructionsRef.current = true; }}
                    className="text-[10px] font-bold uppercase px-2 py-0.5 border border-brutal-black dark:border-neutral-500 hover:bg-brutal-yellow dark:hover:bg-zinc-700 transition-colors"
                  >Edit</button>
                ) : (
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const { saveHeartbeatMd } = await import('../../lib/api');
                          await saveHeartbeatMd(mdDraft, currentChatId || undefined);
                          update({ heartbeat_instructions: mdDraft });
                        } catch { /* best-effort */ }
                        setIsEditingMd(false);
                        isEditingInstructionsRef.current = false;
                      }}
                      className="text-[10px] font-bold uppercase px-2 py-0.5 border border-brutal-black bg-brutal-green dark:bg-green-700 hover:brightness-105 transition-colors"
                    >Save</button>
                    <button
                      type="button"
                      onClick={() => { setIsEditingMd(false); isEditingInstructionsRef.current = false; }}
                      className="text-[10px] font-bold uppercase px-2 py-0.5 border border-brutal-black hover:bg-neutral-200 dark:hover:bg-zinc-700 transition-colors"
                    >Cancel</button>
                  </div>
                )}
              </div>
              {isEditingMd ? (
                <textarea
                  value={mdDraft}
                  onChange={e => setMdDraft(e.target.value)}
                  autoFocus
                  rows={6}
                  placeholder="- Check for updates&#10;- Follow up on previous task"
                  className="w-full bg-white dark:bg-zinc-800 border-2 border-brutal-black px-2 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-700 dark:text-white resize-y"
                />
              ) : (
                <div className="min-h-[3rem] px-2 py-2 font-mono text-xs border border-brutal-black dark:border-neutral-600 bg-white dark:bg-zinc-800 dark:text-neutral-300 whitespace-pre-wrap break-words opacity-80">
                  {config.heartbeat_instructions || <span className="italic text-neutral-400">No instructions yet — click Edit</span>}
                </div>
              )}
            </div>
            {(liveLastRunAt || config.heartbeat_last_run_at) && (
              <div className="text-[10px] text-neutral-500 font-mono mt-1">
                Last run: {new Date(liveLastRunAt || config.heartbeat_last_run_at!).toLocaleString()}
              </div>
            )}
            {liveLastError && (
              <div className="text-[10px] text-red-500 font-mono mt-1 break-all">
                Last error: {liveLastError}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => {
                  if (!currentChatId) return;
                  window.dispatchEvent(new CustomEvent('agui:send-message', {
                    detail: { body: { message: '', chat_id: currentChatId, is_heartbeat: true } },
                  }));
                }}
                className="px-3 py-1 bg-brutal-blue text-white border-2 border-brutal-black font-bold uppercase text-[10px] hover:brightness-110 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none transition-colors"
              >
                Run Now
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-[10px] font-bold uppercase text-brutal-black dark:text-white">{t('config.volumeMounts.label')}</div>

        {/* Global volumes from config file (read-only) */}
        {backendConfig?.globalSandboxVolumes && backendConfig.globalSandboxVolumes.length > 0 && (
          <div className="space-y-1">
            <div className="text-[9px] font-bold uppercase text-brutal-black dark:text-neutral-400 opacity-60">{t('config.volumeMounts.globalFromConfig')}</div>
            <ul className="space-y-1">
              {backendConfig.globalSandboxVolumes.map((vol: string, idx: number) => (
                <li key={`global-${idx}`} className="flex items-center gap-2 bg-brutal-yellow border-3 border-brutal-black px-2 py-1 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <span className="flex-1 font-mono text-xs font-bold truncate" title={vol}>{vol}</span>
                  <span className="text-[9px] font-bold uppercase bg-brutal-black text-white px-1.5 py-0.5 border-2 border-brutal-black">
                    🌍 {t('config.volumeMounts.globalBadge')}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Per-chat volumes (editable) */}
        <div className="space-y-2">
          <div className="text-[9px] font-bold uppercase text-brutal-black dark:text-neutral-400 opacity-60">{t('config.volumeMounts.perChat')}</div>

          <div className="flex flex-col gap-2 p-2 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900">
            <div className="text-[10px] text-brutal-black dark:text-neutral-400 opacity-60 italic">
              {t('config.volumeMounts.manageFromFolder')}
            </div>
          </div>


          {(config.sandbox_volumes || []).length > 0 && (
            <ul className="space-y-1">
              {(config.sandbox_volumes || []).map((vol: string, idx: number) => (
                <li key={idx} className="flex items-center gap-2 bg-white dark:bg-zinc-800 border-3 border-brutal-black px-2 py-1 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
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
          <label className="block font-bold tracking-wide text-brutal-black dark:text-white uppercase">{t('config.mcp.label')}</label>
          <span className="text-[9px] font-bold uppercase text-neutral-500">{t('config.mcp.manageInSettings')}</span>
        </div>
        <div className="space-y-2">
          {servers.length === 0 && (
            <div className="text-[11px] text-brutal-black dark:text-neutral-300 font-bold uppercase">
              <span>{t('config.mcp.noneConfiguredManageInSettings')}</span>
            </div>
          )}
          <ul
            className={`space-y-2 ${servers.length > 4 ? 'max-h-40 overflow-y-auto pr-1' : ''}`}
            style={servers.length > 4 ? { scrollbarGutter: 'stable both-edges' } : undefined}
          >
            {servers.map((s, idx) => (
              <li key={s.name} className="flex items-center gap-2 bg-white dark:bg-zinc-800 border-3 border-brutal-black px-2 py-1 group shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn transition-transform animate-brutal-drop" style={{ animationDelay: `${idx * 0.05}s` }}>
                <input aria-label={t('config.mcp.enableServer')} type="checkbox" checked={s.enabled} onChange={() => toggleServer(s.name)} disabled={loading} className="w-4 h-4 border-2 border-brutal-black accent-brutal-black" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="truncate font-bold text-brutal-black dark:text-white text-xs" title={s.name}>{s.name}</div>
                    <span className={`text-[10px] px-1.5 py-0.5 border-2 font-bold uppercase ${s.enabled ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 dark:bg-zinc-600 text-brutal-black dark:text-white'}`}>{s.enabled ? t('common.on') : t('common.off')}</span>
                  </div>
                  {s.type === 'url' ? (
                    <div className="truncate text-brutal-black dark:text-neutral-400 text-[11px] font-mono font-bold opacity-50" title={s.url}>{s.url}</div>
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
            <div className="text-xs text-brutal-black dark:text-neutral-400 font-mono font-bold">
              {t('config.mcp.enabledUrls', { count: String(Array.isArray(config.mcp_urls) ? config.mcp_urls.length : Object.keys(config.mcp_urls).length) })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
