import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider, tForLocale } from '../../i18n';
import type { ConfigOptions } from '../../types/api';
import {
  CapabilityToolPicker,
  getCapabilities,
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

const translatedCapabilityIds = [
  'filesystem',
  'shell',
  'web',
  'agent',
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
  'GoalTool',
  'TaskCreateTool',
  'TaskUpdateTool',
  'TaskListTool',
  'RenderUITool',
  'AgentTool',
  'AgentListTool',
  'AgentReadTool',
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
    expect(capabilities[0].tools.map(tool => tool.id)).toEqual([
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
      toggleCapabilitySelection(['ReadFileTool'], [
        'RunCommandTool',
        'CheckCommandTool',
      ]),
    ).toEqual(['ReadFileTool', 'RunCommandTool', 'CheckCommandTool']);
    expect(
      toggleCapabilitySelection(
        ['ReadFileTool', 'RunCommandTool', 'CheckCommandTool'],
        ['RunCommandTool', 'CheckCommandTool'],
      ),
    ).toEqual(['ReadFileTool']);
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
        }),
      ),
    );

    expect(html).not.toContain('role="button"');
    expect(html).toMatch(/aria-label="(?:Deactivate Run command|停用运行命令)"/);
  });

  it('localizes capability and tool metadata by stable IDs', () => {
    expect(tForLocale('zh-CN', 'config.toolCatalog.capabilities.shell.name')).toBe('命令执行');
    expect(tForLocale('zh-CN', 'config.toolCatalog.tools.RunCommandTool.description')).toContain('Shell 命令');
  });

  it('uses backend metadata as the English source of truth', () => {
    const key = 'config.toolCatalog.tools.RunCommandTool.description';
    const backendDescription = 'Description supplied by the backend.';

    expect(tForLocale('en', key)).toBe(key);
    expect(
      resolveCatalogText(
        lookupKey => tForLocale('en', lookupKey),
        key,
        backendDescription,
      ),
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
