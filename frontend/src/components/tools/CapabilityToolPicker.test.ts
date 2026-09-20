import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider, tForLocale } from '../../i18n';
import type { ConfigOptions } from '../../types/api';
import {
  CapabilityToolPicker,
  getCapabilities,
  getLockedTools,
  resolveCatalogText,
  toggleCapabilitySelection,
  toggleToolSelection,
} from './CapabilityToolPicker';

const config = {
  tools: ['RunCommandTool', 'CheckCommandTool'],
  toolCapabilities: [
    {
      id: 'shell',
      label: 'Shell',
      description: 'Run and manage commands.',
      tools: [
        {
          id: 'RunCommandTool',
          name: 'Run command',
          description: 'Run bounded commands.',
          runtimeName: 'run_command',
          requiresApproval: true,
        },
        {
          id: 'CheckCommandTool',
          name: 'Check command',
          description: 'Read background output.',
          runtimeName: 'check_command',
          requiresApproval: false,
        },
        {
          id: 'StopCommandTool',
          name: 'Stop command',
          description: 'Stop a process.',
          runtimeName: 'stop_command',
          requiresApproval: true,
        },
      ],
    },
  ],
} as ConfigOptions;

const builtinConfig = {
  tools: ['ReadFileTool', 'GlobTool', 'WriteFileTool'],
  builtinTools: ['ReadFileTool', 'GlobTool'],
  toolCapabilities: [
    {
      id: 'filesystem',
      label: 'Filesystem',
      description: 'Read and write files.',
      tools: [
        {
          id: 'ReadFileTool',
          name: 'Read file',
          description: 'Read a file.',
          runtimeName: 'read_file',
          requiresApproval: false,
          builtin: true,
        },
        {
          id: 'GlobTool',
          name: 'Find files',
          description: 'Find files by pattern.',
          runtimeName: 'glob_search',
          requiresApproval: false,
          builtin: true,
        },
        {
          id: 'WriteFileTool',
          name: 'Write file',
          description: 'Write a file.',
          runtimeName: 'write_file',
          requiresApproval: true,
          deferrable: false,
        },
      ],
    },
  ],
} as ConfigOptions;

const translatedCapabilityIds = [
  'filesystem',
  'shell',
  'web',
  'tasks-goals',
  'orchestration',
  'interaction',
  'creative',
  'memory-recall',
];

const translatedToolIds = [
  'ReadFileTool',
  'WriteFileTool',
  'EditFileTool',
  'GlobTool',
  'GrepTool',
  'RunCommandTool',
  'StartCommandTool',
  'CheckCommandTool',
  'StopCommandTool',
  'BrowsingTool',
  'WebpageTool',
  'WebSearchTool',
  'AskQuestionTool',
  'SkillTool',
  'GoalTool',
  'TaskCreateTool',
  'TaskUpdateTool',
  'TaskListTool',
  'RenderUITool',
  'AgentTool',
  'AgentListTool',
  'AgentReadTool',
  'AgentSendTool',
  'AgentStopTool',
  'ImageGenerationTool',
  'ImageVisionTool',
  'SpeakTool',
  'SocialMessageTool',
  'MemorySearchTool',
  'SessionSearchTool',
];

describe('capability tool picker', () => {
  it('keeps rich metadata while filtering unavailable tools', () => {
    const capabilities = getCapabilities(config);
    expect(capabilities).toHaveLength(1);
    expect(capabilities[0].description).toBe('Run and manage commands.');
    expect(capabilities[0].tools.map((tool) => tool.id)).toEqual([
      'RunCommandTool',
      'CheckCommandTool',
    ]);
    expect(capabilities[0].tools[0].runtimeName).toBe('run_command');
  });

  it('allows each tool to be toggled independently', () => {
    expect(toggleToolSelection(['RunCommandTool'], 'CheckCommandTool')).toEqual([
      'RunCommandTool',
      'CheckCommandTool',
    ]);
    expect(toggleToolSelection(['RunCommandTool'], 'RunCommandTool')).toEqual([]);
  });

  it('toggles the whole capability without losing unrelated selections', () => {
    expect(
      toggleCapabilitySelection(['ReadFileTool'], ['RunCommandTool', 'CheckCommandTool'])
    ).toEqual(['ReadFileTool', 'RunCommandTool', 'CheckCommandTool']);
    expect(
      toggleCapabilitySelection(
        ['ReadFileTool', 'RunCommandTool', 'CheckCommandTool'],
        ['RunCommandTool', 'CheckCommandTool']
      )
    ).toEqual(['ReadFileTool']);
  });

  it('reads locked tools from both the flag and the id list', () => {
    expect(getLockedTools(builtinConfig)).toEqual(new Set(['ReadFileTool', 'GlobTool']));
    expect(getLockedTools(config)).toEqual(new Set());
  });

  it('refuses to turn a builtin off', () => {
    const locked = new Set(['ReadFileTool']);

    expect(toggleToolSelection(['ReadFileTool', 'WriteFileTool'], 'ReadFileTool', locked)).toEqual([
      'ReadFileTool',
      'WriteFileTool',
    ]);
    // Missing from a stale saved selection: toggling adds it rather than no-ops.
    expect(toggleToolSelection(['WriteFileTool'], 'ReadFileTool', locked)).toEqual([
      'WriteFileTool',
      'ReadFileTool',
    ]);
  });

  it('clears a capability down to its builtins', () => {
    const locked = new Set(['ReadFileTool']);
    const tools = ['ReadFileTool', 'WriteFileTool'];

    // Header toggle with every unlocked tool on: clears them, keeps the builtin.
    expect(toggleCapabilitySelection(['ReadFileTool', 'WriteFileTool'], tools, locked)).toEqual([
      'ReadFileTool',
    ]);
    // Builtin alone must not read as "all selected", or the header would be stuck.
    expect(toggleCapabilitySelection(['ReadFileTool'], tools, locked)).toEqual([
      'ReadFileTool',
      'WriteFileTool',
    ]);
  });

  it('renders a builtin as checked, badged and non-interactive', () => {
    const html = renderToStaticMarkup(
      React.createElement(
        I18nProvider,
        null,
        React.createElement(CapabilityToolPicker, {
          backendConfig: builtinConfig,
          selected: [],
          onChange: () => undefined,
        })
      )
    );

    expect(html).toContain('disabled=""');
    expect(html).toMatch(/Built-in|内置/);
    // Two locked tools are checked despite an empty selection; the third is not.
    expect(html.match(/M5 13l4 4L19 7/g)?.length).toBe(2);
    // Locked rows are grey rather than a faded copy of the "selected" green:
    // greyed-and-checked is the usual idiom for "managed, not yours to change".
    // Grey alone reads as unavailable, so the padlock has to carry the rest —
    // it also survives monochrome and colour blindness.
    expect(html.match(/ bg-neutral-300/g)?.length).toBe(2);
    expect(html).not.toContain('bg-brutal-green/60');
    expect(html.match(/M8 11V7a4 4 0 0 1 8 0v4/g)?.length).toBe(2);
  });

  it('marks an unchecked non-deferrable tool as off, and says the rest stay searchable', () => {
    const html = renderToStaticMarkup(
      React.createElement(
        I18nProvider,
        null,
        React.createElement(CapabilityToolPicker, {
          backendConfig: builtinConfig,
          selected: [],
          onChange: () => undefined,
        })
      )
    );

    // Unchecking usually demotes a tool to the ToolSearch pool rather than
    // denying it, so the footnote has to be there and the OFF badge has to be
    // rare — only the tool that really is unreachable when unchecked.
    expect(html).toMatch(/mid-task|执行过程中/);
    expect(html.match(/>Off<|>已关闭</g)?.length).toBe(1);
  });

  it('renders selection and deactivation as sibling buttons', () => {
    const html = renderToStaticMarkup(
      React.createElement(
        I18nProvider,
        null,
        React.createElement(CapabilityToolPicker, {
          backendConfig: config,
          selected: [],
          onChange: () => undefined,
          activatedByAI: new Set(['RunCommandTool']),
          onDeactivate: () => undefined,
        })
      )
    );

    expect(html).not.toContain('role="button"');
    expect(html).toMatch(/aria-label="(?:Deactivate Run command|停用运行命令)"/);
  });

  it('localizes capability and tool metadata by stable IDs', () => {
    expect(tForLocale('zh-CN', 'config.toolCatalog.capabilities.shell.name')).toBe('命令执行');
    expect(tForLocale('zh-CN', 'config.toolCatalog.tools.RunCommandTool.description')).toContain(
      'Shell 命令'
    );
  });

  it('uses backend metadata as the English source of truth', () => {
    const key = 'config.toolCatalog.tools.RunCommandTool.description';
    const backendDescription = 'Description supplied by the backend.';

    expect(tForLocale('en', key)).toBe(key);
    expect(
      resolveCatalogText((lookupKey) => tForLocale('en', lookupKey), key, backendDescription)
    ).toBe(backendDescription);
  });

  it('has Simplified Chinese overrides for every built-in catalog entry', () => {
    for (const capabilityId of translatedCapabilityIds) {
      for (const field of ['name', 'description']) {
        const key = `config.toolCatalog.capabilities.${capabilityId}.${field}`;
        expect(tForLocale('zh-CN', key)).not.toBe(key);
      }
    }
    for (const toolId of translatedToolIds) {
      for (const field of ['name', 'description']) {
        const key = `config.toolCatalog.tools.${toolId}.${field}`;
        expect(tForLocale('zh-CN', key)).not.toBe(key);
      }
    }
  });
});
