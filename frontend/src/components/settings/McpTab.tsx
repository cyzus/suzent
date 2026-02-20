import React, { useState } from 'react';

import { addMcpServer, fetchMcpServers, removeMcpServer, setMcpServerEnabled } from '../../lib/api';
import { useI18n } from '../../i18n';
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

    const handleAddServer = async () => {
        setLoading(true);
        try {
            if (addType === 'url') {
                if (!srvUrl.trim()) return;
                try { new URL(srvUrl); } catch { return; }
                // Parse headers from KEY=value format
                let headers: Record<string, string> | undefined;
                if (srvHeaders.trim()) {
                    headers = {};
                    for (const pair of srvHeaders.split(',')) {
                        const [k, v] = pair.split('=').map(s => s.trim());
                        if (k && v) headers[k] = v;
                    }
                }
                await addMcpServer(srvName.trim() || new URL(srvUrl).host, srvUrl.trim(), undefined, headers);
            } else {
                if (!stdioCmd.trim()) return;
                const args = stdioArgs.trim()
                    ? stdioArgs.split(',').map(s => s.trim()).filter(Boolean)
                    : undefined;
                let env: Record<string, string> | undefined;
                if (stdioEnv.trim()) {
                    env = {};
                    for (const pair of stdioEnv.split(',')) {
                        const [k, v] = pair.split('=').map(s => s.trim());
                        if (k && v) env[k] = v;
                    }
                }
                await addMcpServer(srvName.trim() || stdioCmd.trim(), undefined, { command: stdioCmd.trim(), args, env });
            }
            // Clear form
            setSrvName('');
            setSrvUrl('');
            setSrvHeaders('');
            setStdioCmd('');
            setStdioArgs('');
            setStdioEnv('');
            // Refresh servers
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
        } finally {
            setLoading(false);
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
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black">{t('settings.categories.mcp')}</h2>
            </div>

            {/* Add MCP Server Card */}
            <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.mcp.addNewServerTitle')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.mcp.addNewServerDesc')}</p>
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
                            className="w-40 bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                        />
                    </div>

                    {addType === 'url' ? (
                        <div className="space-y-2">
                            <input
                                value={srvUrl}
                                onChange={e => setSrvUrl(e.target.value)}
                                placeholder={t('config.mcp.urlPlaceholder')}
                                className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                            />
                            <input
                                value={srvHeaders}
                                onChange={e => setSrvHeaders(e.target.value)}
                                placeholder={t('settings.mcp.headersPlaceholder')}
                                className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                            />
                        </div>
                    ) : (
                        <div className="space-y-2">
                            <input
                                value={stdioCmd}
                                onChange={e => setStdioCmd(e.target.value)}
                                placeholder={t('settings.mcp.commandPlaceholder')}
                                className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                            />
                            <input
                                value={stdioArgs}
                                onChange={e => setStdioArgs(e.target.value)}
                                placeholder={t('settings.mcp.argsPlaceholder')}
                                className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                            />
                            <input
                                value={stdioEnv}
                                onChange={e => setStdioEnv(e.target.value)}
                                placeholder={t('settings.mcp.envPlaceholder')}
                                className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
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
            <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-black border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.mcp.configuredServersTitle')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.mcp.configuredServersDesc')}</p>
                    </div>
                </div>

                {serverList.length === 0 ? (
                    <div className="text-center py-8 text-neutral-500 font-bold uppercase">
                        {t('settings.mcp.noneConfiguredYet')}
                    </div>
                ) : (
                    <div className="space-y-3">
                        {serverList.map((server) => (
                            <div
                                key={server.name}
                                className="flex items-center gap-4 bg-neutral-50 border-2 border-brutal-black p-4 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                            >
                                <input
                                    type="checkbox"
                                    checked={server.enabled}
                                    onChange={() => handleToggleServer(server)}
                                    disabled={loading}
                                    className="w-5 h-5 border-2 border-brutal-black accent-brutal-black"
                                />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold text-brutal-black">{server.name}</span>
                                        <span className={`text-[10px] px-2 py-0.5 border-2 font-bold uppercase ${server.enabled ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 text-brutal-black'}`}>
                                            {server.enabled ? t('common.on') : t('common.off')}
                                        </span>
                                        <span className="text-[10px] px-2 py-0.5 border border-neutral-400 text-neutral-500 uppercase">
                                            {server.type}
                                        </span>
                                    </div>
                                    {server.type === 'url' ? (
                                        <div className="text-xs font-mono text-neutral-500 truncate" title={server.url}>{server.url}</div>
                                    ) : (
                                        <div className="text-xs font-mono text-neutral-500 truncate">
                                            {server.command}
                                            {server.args && server.args.length > 0 && ` [${server.args.join(', ')}]`}
                                        </div>
                                    )}
                                </div>
                                <button
                                    onClick={() => handleRemoveServer(server)}
                                    disabled={loading}
                                    className="px-3 py-1 bg-brutal-red text-white border-2 border-brutal-black font-bold text-xs uppercase hover:bg-red-600 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                                >
                                    {t('common.remove')}
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
