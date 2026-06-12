import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import { addMcpServer, updateMcpServer, fetchMcpServers, removeMcpServer, setMcpServerEnabled, testMcpServer, type McpProbeResult } from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';

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
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black dark:text-white">{t('settings.mcp.title')}</h2>
            </div>

            {/* Add MCP Server Card */}
            <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.mcp.addNewServerTitle')}</h3>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.mcp.addNewServerDesc')}</p>
                    </div>
                </div>

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
            </div>

            {/* Server List Card */}
            <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-black border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.mcp.configuredServersTitle')}</h3>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.mcp.configuredServersDesc')}</p>
                    </div>
                </div>

                {serverList.length === 0 ? (
                    <div className="text-center py-8 text-neutral-500 dark:text-neutral-400 font-bold uppercase">
                        {t('settings.mcp.noServersConfigured')}
                    </div>
                ) : (
                    <div className="space-y-3">
                        {serverList.map((server) => (
                            <div
                                key={server.name}
                                className="bg-neutral-50 dark:bg-zinc-900 border-2 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                            >
                              <div className="flex items-center gap-4 p-4">
                                <input
                                    type="checkbox"
                                    checked={server.enabled}
                                    onChange={() => handleToggleServer(server)}
                                    disabled={loading}
                                    className="w-5 h-5 border-2 border-brutal-black accent-brutal-black"
                                />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold text-brutal-black dark:text-white">{server.name}</span>
                                        <span className={`text-[10px] px-2 py-0.5 border-2 font-bold uppercase ${server.enabled ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 text-brutal-black'}`}>
                                            {server.enabled ? t('common.on') : t('common.off')}
                                        </span>
                                        <span className="text-[10px] px-2 py-0.5 border border-neutral-400 text-neutral-500 dark:text-neutral-400 uppercase">
                                            {server.type === 'url' ? t('config.mcp.url') : t('config.mcp.stdio')}
                                        </span>
                                    </div>
                                    {server.type === 'url' ? (
                                        <div className="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate" title={server.url}>{server.url}</div>
                                    ) : (
                                        <div className="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate">
                                            {server.command}
                                            {server.args && server.args.length > 0 && ` [${server.args.join(', ')}]`}
                                        </div>
                                    )}
                                    {probes[server.name] && (
                                        probes[server.name].testing ? (
                                            <div className="text-[11px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mt-1">{t('settings.mcp.testing')}</div>
                                        ) : probes[server.name].ok ? (
                                            <div className="text-[11px] font-bold uppercase text-green-600 dark:text-green-400 mt-1" title={t('settings.mcp.reachable')}>
                                                <button
                                                    type="button"
                                                    onClick={() => setExpandedTools(prev => ({ ...prev, [server.name]: !prev[server.name] }))}
                                                    className="hover:underline"
                                                >
                                                    ● {t('settings.mcp.reachable')} ({probes[server.name].count ?? 0})
                                                    {(probes[server.name].tools?.length ?? 0) > 0 && (expandedTools[server.name] ? ' ▾' : ' ▸')}
                                                </button>
                                            </div>
                                        ) : (
                                            <div className="text-[11px] font-bold uppercase text-brutal-red mt-1 truncate" title={probes[server.name].error}>
                                                ● {t('settings.mcp.unreachable')}: {probes[server.name].error}
                                            </div>
                                        )
                                    )}
                                    {probes[server.name]?.ok && expandedTools[server.name] && (probes[server.name].tools?.length ?? 0) > 0 && (
                                        <ul className="mt-1 space-y-0.5">
                                            {probes[server.name].tools!.map(tool => (
                                                <li
                                                    key={tool.name}
                                                    className="text-[11px] font-mono text-neutral-600 dark:text-neutral-300 truncate"
                                                    title={tool.description || tool.name}
                                                >
                                                    • {tool.name}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                                <button
                                    onClick={() => handleTestServer(server)}
                                    disabled={loading || probes[server.name]?.testing}
                                    className="px-3 py-1 bg-brutal-blue text-white border-2 border-brutal-black font-bold text-xs uppercase hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                                >
                                    {t('settings.mcp.test')}
                                </button>
                                <button
                                    onClick={() => editDraft?.name === server.name ? setEditDraft(null) : startEdit(server)}
                                    disabled={loading}
                                    className={`px-3 py-1 border-2 border-brutal-black font-bold text-xs uppercase hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50 ${editDraft?.name === server.name ? 'bg-brutal-black text-white' : 'bg-brutal-yellow text-brutal-black'}`}
                                >
                                    {t('common.edit')}
                                </button>
                                <button
                                    onClick={() => handleRemoveServer(server)}
                                    disabled={loading}
                                    className="px-3 py-1 bg-brutal-red text-white border-2 border-brutal-black font-bold text-xs uppercase hover:bg-red-600 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                                >
                                    {t('common.remove')}
                                </button>
                              </div>

                              {editDraft?.name === server.name && (
                                <div className="border-t-2 border-brutal-black p-4 space-y-2 bg-white dark:bg-zinc-800">
                                    <div className="text-[11px] font-bold uppercase text-neutral-500 dark:text-neutral-400">
                                        {t('settings.mcp.editServerTitle')} — {server.name}
                                    </div>
                                    {editDraft.type === 'url' ? (
                                        <>
                                            <input
                                                value={editDraft.url}
                                                onChange={e => setEditDraft({ ...editDraft, url: e.target.value })}
                                                placeholder="https://host/path"
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
                                            />
                                            <input
                                                value={editDraft.headers}
                                                onChange={e => setEditDraft({ ...editDraft, headers: e.target.value })}
                                                placeholder={t('settings.mcp.headersPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
                                            />
                                        </>
                                    ) : (
                                        <>
                                            <input
                                                value={editDraft.command}
                                                onChange={e => setEditDraft({ ...editDraft, command: e.target.value })}
                                                placeholder={t('settings.mcp.commandPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
                                            />
                                            <input
                                                value={editDraft.args}
                                                onChange={e => setEditDraft({ ...editDraft, args: e.target.value })}
                                                placeholder={t('settings.mcp.argsPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
                                            />
                                            <input
                                                value={editDraft.env}
                                                onChange={e => setEditDraft({ ...editDraft, env: e.target.value })}
                                                placeholder={t('settings.mcp.envPlaceholder')}
                                                className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500"
                                            />
                                        </>
                                    )}
                                    <div className="flex gap-2">
                                        <button
                                            onClick={handleSaveEdit}
                                            disabled={editLoading || (editDraft.type === 'url' ? !editDraft.url.trim() : !editDraft.command.trim())}
                                            className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold text-xs uppercase text-brutal-black hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                                        >
                                            {editLoading ? t('settings.mcp.saving') : t('settings.mcp.saveServer')}
                                        </button>
                                        <button
                                            onClick={() => setEditDraft(null)}
                                            disabled={editLoading}
                                            className="px-4 py-2 bg-neutral-200 dark:bg-zinc-700 border-2 border-brutal-black font-bold text-xs uppercase text-brutal-black dark:text-white hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                                        >
                                            {t('common.cancel')}
                                        </button>
                                    </div>
                                </div>
                              )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
