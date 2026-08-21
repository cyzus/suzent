import { describe, it, expect } from 'vitest';
import { buildEngineOptions, engineValue, parseEngineValue } from './engineOptions';
import type { AcpAgentDescriptor } from '../types/api';

const LABELS = {
  models: 'Models',
  acp: 'ACP agents',
  notInstalled: 'Not installed',
  installHint: 'Not installed — add it in Settings',
};

const AGENTS: AcpAgentDescriptor[] = [
  { id: 'claude-code', name: 'Claude Code', status: 'ready' },
  { id: 'codex', name: 'Codex (ACP)', status: 'not_installed', install_command: ['sh', '-c', 'x'] },
  { id: 'bare', name: 'Bare', status: 'not_installed' },
  { id: 'documented', name: 'Documented', status: 'not_installed', docs_url: 'https://x.test' },
];

const build = (over: Partial<Parameters<typeof buildEngineOptions>[0]> = {}) =>
  buildEngineOptions({
    models: ['gpt-5', 'claude-opus-5'],
    agents: AGENTS,
    canChooseRuntime: true,
    labels: LABELS,
    ...over,
  });

describe('buildEngineOptions', () => {
  it('lists models first, then ACP agents in their own group', () => {
    const options = build();
    expect(options.slice(0, 2).map(o => o.label)).toEqual(['gpt-5', 'claude-opus-5']);
    expect(options.slice(0, 2).every(o => o.group === 'Models')).toBe(true);
    expect(options.slice(2).every(o => o.group === 'ACP agents')).toBe(true);
  });

  it('hides agents that are not installed instead of greying them out', () => {
    const values = build().map(o => o.value);
    expect(values).toContain('acp:claude-code');
    expect(values).not.toContain('acp:codex');
    expect(values).not.toContain('acp:bare');
  });

  it('keeps a missing agent visible when the chat is already bound to it', () => {
    const byId = Object.fromEntries(
      build({ selectedAgentId: 'codex' }).map(o => [o.value, o]),
    );
    expect(byId['acp:codex'].disabled).toBe(true);
    expect(byId['acp:codex'].hint).toBe(LABELS.installHint);
    expect(byId['acp:bare']).toBeUndefined();
  });

  it('points at the install path only when there is somewhere to point', () => {
    const byId = Object.fromEntries(
      build({ selectedAgentId: 'bare' }).map(o => [o.value, o]),
    );
    expect(byId['acp:bare'].hint).toBe(LABELS.notInstalled);
    expect(byId['acp:claude-code'].hint).toBeUndefined();
  });

  it('treats vendor docs as an install path, the way built-ins now describe one', () => {
    const byId = Object.fromEntries(
      build({ selectedAgentId: 'documented' }).map(o => [o.value, o]),
    );
    expect(byId['acp:documented'].hint).toBe(LABELS.installHint);
  });

  it('drops the ACP group once the chat exists, keeping the agent in use', () => {
    const options = build({ canChooseRuntime: false, selectedAgentId: 'claude-code' });
    const acp = options.filter(o => o.group === LABELS.acp);
    expect(acp.map(o => o.value)).toEqual(['acp:claude-code']);
  });

  it('offers no ACP entries on an existing native chat', () => {
    const options = build({ canChooseRuntime: false });
    expect(options.some(o => o.group === LABELS.acp)).toBe(false);
  });

  it('falls back to the id when an agent has no name', () => {
    const options = build({ agents: [{ id: 'x', name: '', status: 'ready' }] });
    expect(options.at(-1)!.label).toBe('ACP · x');
  });
});

describe('engineValue / parseEngineValue', () => {
  it('round-trips a model selection', () => {
    const v = engineValue({ isAcpRuntime: false, model: 'gpt-5' });
    expect(parseEngineValue(v)).toEqual({ kind: 'model', model: 'gpt-5' });
  });

  it('round-trips an ACP selection', () => {
    const v = engineValue({ isAcpRuntime: true, acpAgentId: 'claude-code', model: 'gpt-5' });
    expect(parseEngineValue(v)).toEqual({ kind: 'acp', agentId: 'claude-code' });
  });

  it('stays on the model when ACP is flagged without an agent', () => {
    const v = engineValue({ isAcpRuntime: true, model: 'gpt-5' });
    expect(parseEngineValue(v)).toEqual({ kind: 'model', model: 'gpt-5' });
  });

  it('matches the value the option list uses, so the button resolves a label', () => {
    const v = engineValue({ isAcpRuntime: true, acpAgentId: 'claude-code' });
    expect(build().some(o => o.value === v)).toBe(true);
  });

  it('tolerates a model id containing a colon', () => {
    const v = engineValue({ isAcpRuntime: false, model: 'chatgpt/gpt-5.6-sol:latest' });
    expect(parseEngineValue(v)).toEqual({ kind: 'model', model: 'chatgpt/gpt-5.6-sol:latest' });
  });
});
