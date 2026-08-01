import { describe, expect, it } from 'vitest';

import type { ConfigOptions } from '../../types/api';
import {
  getCapabilities,
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
});
