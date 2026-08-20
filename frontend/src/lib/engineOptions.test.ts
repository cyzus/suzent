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
  { id: 'codex-acp', name: 'Codex (ACP)', status: 'not_installed', install_command: ['sh', '-c', 'x'] },
  { id: 'bare', name: 'Bare', status: 'not_installed' },
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

  it('never offers an agent whose binary is missing', () => {
    const options = build();
    const byId = Object.fromEntries(options.map(o => [o.value, o]));
    expect(byId['acp:claude-code'].disabled).toBeFalsy();
    expect(byId['acp:codex-acp'].disabled).toBe(true);
    expect(byId['acp:bare'].disabled).toBe(true);
  });

  it('points at the install path only when there is an install command', () => {
    const byId = Object.fromEntries(build().map(o => [o.value, o]));
    expect(byId['acp:codex-acp'].hint).toBe(LABELS.installHint);
    expect(byId['acp:bare'].hint).toBe(LABELS.notInstalled);
    expect(byId['acp:claude-code'].hint).toBeUndefined();
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
