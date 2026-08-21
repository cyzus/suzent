import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAcpAgents } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
});

const respond = (agents: unknown[]) => {
  // `getApiBase` reads window to find the Tauri-injected backend port.
  vi.stubGlobal('window', {});
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ agents }), { status: 200 })),
  );
};

describe('fetchAcpAgents', () => {
  // The mapping is field-by-field, so anything the backend adds is silently
  // dropped until it is listed here. The setup panel depends on both.
  it('carries the setup fields through to the descriptor', async () => {
    respond([
      {
        id: 'codex',
        name: 'Codex',
        status: 'not_installed',
        docs_url: 'https://developers.openai.com/codex/cli/',
        adapter_package: '@agentclientprotocol/codex-acp',
      },
    ]);

    const [agent] = await fetchAcpAgents();

    expect(agent.docs_url).toBe('https://developers.openai.com/codex/cli/');
    expect(agent.adapter_package).toBe('@agentclientprotocol/codex-acp');
  });

  it('leaves the setup fields undefined for an agent that has none', async () => {
    respond([{ id: 'bare', name: 'Bare', status: 'ready' }]);

    const [agent] = await fetchAcpAgents();

    expect(agent.docs_url).toBeUndefined();
    expect(agent.adapter_package).toBeUndefined();
  });
});
