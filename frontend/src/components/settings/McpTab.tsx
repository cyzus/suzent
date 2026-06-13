import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import { addMcpServer, updateMcpServer, fetchMcpServers, removeMcpServer, setMcpServerEnabled, testMcpServer, type McpProbeResult } from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';
import { SettingsHeader } from './SettingsHeader';
import { SectionCardHeader, SettingsCard, SettingsListItem, SettingsListAction } from './SettingsCard';
import { BrutalOnOff } from '../BrutalOnOff';

type MCPUrlServer = {
    type: 'url';
    name: string;
    url: string;
    headers?: Record<string, string>;
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

interface McpTabProps {
    serverList: MCPServer[];
    onServerListChange: (servers: MCPServer[]) => void;
    onMcpServersRefresh: (data: { urls: Record<string, string>; stdio: Record<string, any>; enabled: Record<string, boolean> }) => void;
}

export function McpTab({
    serverList,
    onServerListChange,
    onMcpServersRefresh,
}: McpTabProps): React.ReactElement {
    const { t } = useI18n();
    const [srvName, setSrvName] = useState('');
    const [srvUrl, setSrvUrl] = useState('');
    const [srvHeaders, setSrvHeaders] = useState('');
    const [stdioCmd, setStdioCmd] = useState('');
    const [stdioArgs, setStdioArgs] = useState('');
    const [stdioEnv, setStdioEnv] = useState('');
    const [addType, setAddType] = useState<'url' | 'stdio'>('url');
    const [loading, setLoading] = useState(false);
    // In-progress inline edit for one server, or null. Transport mirrors the
    // server's own type (the name and transport kind are not editable here).
    type EditDraft = { name: string; type: 'url' | 'stdio'; url: string; headers: string; command: string; args: string; env: string };
    const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
    const [editLoading, setEditLoading] = useState(false);
    // Per-server probe results, keyed by server name. `testing` flags an in-flight probe.
    const [probes, setProbes] = useState<Record<string, McpProbeResult & { testing?: boolean }>>({});
    // Which servers have their tool list expanded.
    const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});

    const parseKv = (raw: string): Record<string, string> | undefined => {
        if (!raw.trim()) return undefined;
        const out: Record<string, string> = {};
        for (const pair of raw.split(',')) {
            const [k, v] = pair.split('=').map(s => s.trim());
            if (k && v) out[k] = v;
        }
        return Object.keys(out).length ? out : undefined;
    };

    const clearAddForm = () => {
        setSrvName('');
        setSrvUrl('');
        setSrvHeaders('');
        setStdioCmd('');
        setStdioArgs('');
        setStdioEnv('');
    };

    const refreshServerList = async () => {
        const data = await fetchMcpServers();
        onMcpServersRefresh(data);
        const urls = data.urls || {};
        const stdio = data.stdio || {};
        const enabled = data.enabled || {};
        const urlServers: MCPServer[] = Object.entries(urls).map(([name, url]) => ({
            type: 'url', name, url: String(url), enabled: !!enabled[name]
        }));
        const stdioServers: MCPServer[] = Object.entries(stdio).map(([name, params]: [string, any]) => ({
            type: 'stdio', name, command: params.command, args: params.args, env: params.env, enabled: !!enabled[name]
        }));
        onServerListChange([...urlServers, ...stdioServers]);
    };

    const startEdit = (server: MCPServer) => {
        setEditDraft(server.type === 'url'
            ? {
                name: server.name, type: 'url',
                url: server.url,
                headers: Object.entries(server.headers || {}).map(([k, v]) => `${k}=${v}`).join(', '),
                command: '', args: '', env: '',
            }
            : {
                name: server.name, type: 'stdio',
                url: '', headers: '',
                command: server.command,
                args: (server.args || []).join(', '),
                env: Object.entries(server.env || {}).map(([k, v]) => `${k}=${v}`).join(', '),
            });
    };

    const handleAddServer = async () => {
        setLoading(true);
        try {
            let addedName: string;
            let probe: McpProbeResult | undefined;
            if (addType === 'url') {
                if (!srvUrl.trim()) return;
                try { new URL(srvUrl); } catch { return; }
                const headers = parseKv(srvHeaders);
                addedName = srvName.trim() || new URL(srvUrl).host;
                probe = await addMcpServer(addedName, srvUrl.trim(), undefined, headers);
            } else {
                if (!stdioCmd.trim()) return;
                const args = stdioArgs.trim()
                    ? stdioArgs.split(',').map(s => s.trim()).filter(Boolean)
                    : undefined;
                const env = parseKv(stdioEnv);
                addedName = srvName.trim() || stdioCmd.trim();
                probe = await addMcpServer(addedName, undefined, { command: stdioCmd.trim(), args, env });
            }
            if (probe) setProbes(prev => ({ ...prev, [addedName]: probe! }));
            clearAddForm();
            await refreshServerList();
        } finally {
            setLoading(false);
        }
    };

    const handleSaveEdit = async () => {
        if (!editDraft) return;
        setEditLoading(true);
        try {
            const name = editDraft.name;
            let probe: McpProbeResult | undefined;
            if (editDraft.type === 'url') {
                if (!editDraft.url.trim()) return;
                try { new URL(editDraft.url); } catch { return; }
                probe = await updateMcpServer(name, editDraft.url.trim(), undefined, parseKv(editDraft.headers));
            } else {
                if (!editDraft.command.trim()) return;
                const args = editDraft.args.trim()
                    ? editDraft.args.split(',').map(s => s.trim()).filter(Boolean)
                    : undefined;
                probe = await updateMcpServer(name, undefined, { command: editDraft.command.trim(), args, env: parseKv(editDraft.env) });
            }
            if (probe) setProbes(prev => ({ ...prev, [name]: probe! }));
            setEditDraft(null);
            await refreshServerList();
        } finally {
            setEditLoading(false);
        }
    };

    const handleToggleServer = async (server: MCPServer) => {
        setLoading(true);
        try {
            await setMcpServerEnabled(server.name, !server.enabled);
            onServerListChange(serverList.map(s =>
                s.name === server.name ? { ...s, enabled: !s.enabled } : s
            ));
        } finally {
            setLoading(false);
        }
    };

    const handleRemoveServer = async (server: MCPServer) => {
        setLoading(true);
        try {
            await removeMcpServer(server.name);
            onServerListChange(serverList.filter(s => s.name !== server.name));
            setProbes(prev => {
                const next = { ...prev };
                delete next[server.name];
                return next;
            });
        } finally {
            setLoading(false);
        }
    };

    const handleTestServer = async (server: MCPServer) => {
        setProbes(prev => ({ ...prev, [server.name]: { ok: false, testing: true } }));
        try {
            const result = await testMcpServer(server.name);
            setProbes(prev => ({ ...prev, [server.name]: result }));
        } catch (e) {
            setProbes(prev => ({ ...prev, [server.name]: { ok: false, error: String(e) } }));
        }
    };

    return (
        <div className="space-y-6">
            <SettingsHeader title={t('settings.mcp.title')} subtitle={t('settings.mcp.subtitle')} />

            {/* Add MCP Server Card */}
            <SettingsCard>
                <SectionCardHeader
                    iconTone="blue"
                    icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>}
                    title={t('settings.mcp.addNewServerTitle')}
                    description={t('settings.mcp.addNewServerDesc')}
                />

                <div className="space-y-4">
                    <div className="flex gap-2">
                        <BrutalSelect
                            value={addType}
                            onChange={val => setAddType(val as 'url' | 'stdio')}
                            options={[{ value: 'url', label: t('config.mcp.url') }, { value: 'stdio', label: t('config.mcp.stdio') }]}
                            className="w-32"
                        />
                        <input
                            value={srvName}
                            onChange={e => setSrvName(e.target.value)}
                            placeholder={t('settings.mcp.nameOptionalPlaceholder')}
                            className="w-40 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                        />
                    </div>

                    {addType === 'url' ? (
                        <div className="space-y-2">
                            <input
                                value={srvUrl}
                                onChange={e => setSrvUrl(e.target.value)}
                                placeholder="https://host/path"
                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                            />
                            <input
                                value={srvHeaders}
                                onChange={e => setSrvHeaders(e.target.value)}
                                placeholder={t('settings.mcp.headersPlaceholder')}
                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                            />
                        </div>
                    ) : (
                        <div className="space-y-2">
                            <input
                                value={stdioCmd}
                                onChange={e => setStdioCmd(e.target.value)}
                                placeholder={t('settings.mcp.commandPlaceholder')}
                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                            />
                            <input
                                value={stdioArgs}
                                onChange={e => setStdioArgs(e.target.value)}
                                placeholder={t('settings.mcp.argsPlaceholder')}
                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                            />
                            <input
                                value={stdioEnv}
                                onChange={e => setStdioEnv(e.target.value)}
                                placeholder={t('settings.mcp.envPlaceholder')}
                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                            />
                        </div>
                    )}

                    <button
                        onClick={handleAddServer}
                        disabled={loading || (addType === 'url' ? !srvUrl.trim() : !stdioCmd.trim())}
                        className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-brutal-black hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                    >
                        {loading ? t('settings.mcp.adding') : t('settings.mcp.addServer')}
                    </button>
                </div>
            </SettingsCard>

            {/* Server List Card */}
            <SettingsCard>
                <SectionCardHeader
                    iconTone="black"
                    icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>}
                    title={t('settings.mcp.configuredServersTitle')}
                    description={t('settings.mcp.configuredServersDesc')}
                />

                {serverList.length === 0 ? (
                    <div className="text-center py-8 text-neutral-500 dark:text-neutral-400 font-bold uppercase">
                        {t('settings.mcp.noServersConfigured')}
                    </div>
                ) : (
                    <div className="space-y-4">
                        {serverList.map((server) => (
                            <SettingsListItem key={server.name}>
                              <div className="flex flex-col md:flex-row items-start md:items-center gap-4 p-4 md:p-5 relative overflow-hidden">
                                
                                <div className="relative z-10 shrink-0 mt-1 md:mt-0">
                                    <BrutalOnOff
                                        size="md"
                                        checked={server.enabled}
                                        onChange={() => handleToggleServer(server)}
                                        disabled={loading}
                                    />
                                </div>
                                <div className="flex-1 min-w-0 relative z-10 w-full">
                                    <div className="flex items-center gap-3 mb-2">
                                        <span className="text-lg font-black uppercase tracking-wide text-brutal-black dark:text-white truncate">
                                            {server.name}
                                        </span>
                                        <span className={`text-[10px] font-bold px-2 py-0.5 border-2 border-brutal-black shadow-[1px_1px_0_0_#000] uppercase ${server.type === 'url' ? 'bg-brutal-blue text-white' : 'bg-brutal-yellow text-brutal-black'}`}>
                                            {server.type === 'url' ? t('config.mcp.url') : t('config.mcp.stdio')}
                                        </span>
                                    </div>
                                    <div className="bg-white dark:bg-zinc-800 border-2 border-dashed border-brutal-black/40 dark:border-white/20 p-2 text-xs font-mono text-neutral-600 dark:text-neutral-300 truncate rounded-sm">
                                        {server.type === 'url' ? (
                                            <span title={server.url}>{server.url}</span>
                                        ) : (
                                            <span title={`${server.command} ${server.args?.join(' ') || ''}`}>
                                                <span className="font-bold text-brutal-black dark:text-white">{server.command}</span>
                                                {server.args && server.args.length > 0 && ` ${server.args.join(' ')}`}
                                            </span>
                                        )}
                                    </div>
                                    
                                    {probes[server.name] && (
                                        <div className="mt-3">
                                            {probes[server.name].testing ? (
                                                <div className="inline-flex items-center gap-1.5 px-2 py-1 bg-neutral-200 dark:bg-zinc-700 border border-brutal-black text-[10px] font-bold uppercase text-neutral-600 dark:text-neutral-300">
                                                    <span className="text-sm leading-none">⚙</span> {t('settings.mcp.testing')}
                                                </div>
                                            ) : probes[server.name].ok ? (
                                                <div className="inline-flex items-center gap-2">
                                                    <div className="inline-flex items-center gap-1.5 px-2 py-1 bg-green-100 dark:bg-green-900/30 border border-brutal-black text-[10px] font-bold uppercase text-green-700 dark:text-green-400" title={t('settings.mcp.reachable')}>
                                                        <span className="w-2 h-2 bg-green-500 rounded-full border border-brutal-black" />
                                                        {t('settings.mcp.reachable')} ({probes[server.name].count ?? 0})
                                                    </div>
                                                    {(probes[server.name].tools?.length ?? 0) > 0 && (
                                                        <button
                                                            type="button"
                                                            onClick={() => setExpandedTools(prev => ({ ...prev, [server.name]: !prev[server.name] }))}
                                                            className="text-[10px] font-bold uppercase text-brutal-blue dark:text-blue-400 hover:underline hover:text-blue-600"
                                                        >
                                                            {expandedTools[server.name] ? '[-]' : '[+]'} {t('settings.mcp.viewTools')}
                                                        </button>
                                                    )}
                                                </div>
                                            ) : (
                                                <div className="inline-flex items-center gap-1.5 px-2 py-1 bg-red-100 dark:bg-red-900/30 border border-brutal-black text-[10px] font-bold uppercase text-brutal-red truncate max-w-full" title={probes[server.name].error}>
                                                    <span className="text-brutal-red text-sm leading-none">⚠</span>
                                                    <span className="truncate">{t('settings.mcp.unreachable')}: {probes[server.name].error}</span>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                    {probes[server.name]?.ok && expandedTools[server.name] && (probes[server.name].tools?.length ?? 0) > 0 && (
                                        <ul className="mt-3 space-y-1 bg-neutral-100 dark:bg-zinc-800 border border-brutal-black p-3 max-h-48 overflow-y-auto">
                                            {probes[server.name].tools!.map(tool => (
                                                <li
                                                    key={tool.name}
                                                    className="flex flex-col gap-0.5 text-[11px] font-mono border-b border-neutral-300 dark:border-neutral-700 pb-1 last:border-0 last:pb-0"
                                                    title={tool.description || tool.name}
                                                >
                                                    <span className="font-bold text-brutal-blue dark:text-blue-400">{tool.name}</span>
                                                    {tool.description && <span className="text-neutral-500 truncate">{tool.description}</span>}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                                <div className="flex gap-2 shrink-0 relative z-10 w-full md:w-auto mt-3 md:mt-0 justify-end md:self-start md:ml-4">
                                    <SettingsListAction
                                        tone="blue"
                                        onClick={() => handleTestServer(server)}
                                        disabled={loading || probes[server.name]?.testing}
                                    >
                                        {t('settings.mcp.test')}
                                    </SettingsListAction>
                                    <SettingsListAction
                                        active={editDraft?.name === server.name}
                                        onClick={() => editDraft?.name === server.name ? setEditDraft(null) : startEdit(server)}
                                        disabled={loading}
                                    >
                                        {t('common.edit')}
                                    </SettingsListAction>
                                    <SettingsListAction
                                        tone="red"
                                        onClick={() => handleRemoveServer(server)}
                                        disabled={loading}
                                    >
                                        {t('common.remove')}
                                    </SettingsListAction>
                                </div>
                              </div>
 
                              {editDraft?.name === server.name && (
                                <div className="border-t-[3px] border-brutal-black p-5 space-y-3 bg-neutral-100 dark:bg-zinc-800">
                                    <div className="text-[12px] font-black uppercase tracking-wider text-brutal-black dark:text-white flex items-center gap-2">
                                        <span className="w-2 h-2 bg-brutal-yellow border border-brutal-black inline-block" />
                                        {t('settings.mcp.editServerTitle')} — <span className="text-brutal-blue dark:text-blue-400">{server.name}</span>
                                    </div>
                                    {editDraft.type === 'url' ? (
                                        <div className="space-y-2">
                                            <input
                                                value={editDraft.url}
                                                onChange={e => setEditDraft({ ...editDraft, url: e.target.value })}
                                                placeholder="https://host/path"
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs shadow-[2px_2px_0_0_#000] focus:outline-none focus:translate-y-[2px] focus:translate-x-[2px] focus:shadow-none transition-all dark:text-white dark:placeholder-neutral-500"
                                            />
                                            <input
                                                value={editDraft.headers}
                                                onChange={e => setEditDraft({ ...editDraft, headers: e.target.value })}
                                                placeholder={t('settings.mcp.headersPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs shadow-[2px_2px_0_0_#000] focus:outline-none focus:translate-y-[2px] focus:translate-x-[2px] focus:shadow-none transition-all dark:text-white dark:placeholder-neutral-500"
                                            />
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            <input
                                                value={editDraft.command}
                                                onChange={e => setEditDraft({ ...editDraft, command: e.target.value })}
                                                placeholder={t('settings.mcp.commandPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs shadow-[2px_2px_0_0_#000] focus:outline-none focus:translate-y-[2px] focus:translate-x-[2px] focus:shadow-none transition-all dark:text-white dark:placeholder-neutral-500"
                                            />
                                            <input
                                                value={editDraft.args}
                                                onChange={e => setEditDraft({ ...editDraft, args: e.target.value })}
                                                placeholder={t('settings.mcp.argsPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs shadow-[2px_2px_0_0_#000] focus:outline-none focus:translate-y-[2px] focus:translate-x-[2px] focus:shadow-none transition-all dark:text-white dark:placeholder-neutral-500"
                                            />
                                            <input
                                                value={editDraft.env}
                                                onChange={e => setEditDraft({ ...editDraft, env: e.target.value })}
                                                placeholder={t('settings.mcp.envPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs shadow-[2px_2px_0_0_#000] focus:outline-none focus:translate-y-[2px] focus:translate-x-[2px] focus:shadow-none transition-all dark:text-white dark:placeholder-neutral-500"
                                            />
                                        </div>
                                    )}
                                    <div className="flex gap-3 pt-2">
                                        <SettingsListAction
                                            tone="blue"
                                            onClick={handleSaveEdit}
                                            disabled={editLoading || (editDraft.type === 'url' ? !editDraft.url.trim() : !editDraft.command.trim())}
                                        >
                                            {editLoading ? t('settings.mcp.saving') : t('settings.mcp.saveServer')}
                                        </SettingsListAction>
                                        <SettingsListAction
                                            onClick={() => setEditDraft(null)}
                                            disabled={editLoading}
                                        >
                                            {t('common.cancel')}
                                        </SettingsListAction>
                                    </div>
                                </div>
                              )}
                            </SettingsListItem>
                        ))}
                    </div>
                )}
            </SettingsCard>
        </div>
    );
}
