import React from 'react';

import { useI18n } from '../../i18n';
import type { ConfigOptions, ToolCapabilityOption } from '../../types/api';

type CapabilityToolPickerProps = {
  backendConfig: ConfigOptions;
  selected: string[];
  activatedByAI?: Set<string>;
  onChange: (tools: string[]) => void;
  onDeactivate?: (tool: string) => void;
  emptyMessage?: string;
  compact?: boolean;
};

const formatLabel = (tool: string): string =>
  tool.replace(/Tool$/, '').replace(/([a-z])([A-Z])/g, '$1 $2');

export function getCapabilities(config: ConfigOptions): ToolCapabilityOption[] {
  const available = new Set(Array.isArray(config.tools) ? config.tools : []);
  if (config.toolCapabilities?.length) {
    return config.toolCapabilities
      .map(capability => ({
        ...capability,
        tools: capability.tools.filter(tool => available.has(tool.id)),
      }))
      .filter(capability => capability.tools.length > 0);
  }

  const groups = config.toolGroups ?? [];
  const known = new Set(groups.flatMap(group => group.tools));
  const fallback = groups.map((group, index) => ({
    id: `legacy-${index}`,
    label: group.label,
    description: '',
    tools: group.tools.filter(tool => available.has(tool)).map(tool => ({
      id: tool,
      name: formatLabel(tool),
      description: '',
      runtimeName: '',
      requiresApproval: false,
    })),
  }));
  const other = [...available].filter(tool => !known.has(tool));
  if (other.length) {
    fallback.push({
      id: 'other',
      label: 'Other',
      description: '',
      tools: other.map(tool => ({
        id: tool,
        name: formatLabel(tool),
        description: '',
        runtimeName: '',
        requiresApproval: false,
      })),
    });
  }
  return fallback.filter(capability => capability.tools.length > 0);
}

export function toggleToolSelection(selected: string[], tool: string): string[] {
  return selected.includes(tool)
    ? selected.filter(value => value !== tool)
    : [...selected, tool];
}

export function toggleCapabilitySelection(selected: string[], tools: string[]): string[] {
  const allSelected = tools.every(tool => selected.includes(tool));
  return allSelected
    ? selected.filter(tool => !tools.includes(tool))
    : [...new Set([...selected, ...tools])];
}

export function CapabilityToolPicker({
  backendConfig,
  selected,
  activatedByAI = new Set<string>(),
  onChange,
  onDeactivate,
  emptyMessage,
  compact = false,
}: CapabilityToolPickerProps): React.ReactElement {
  const { t } = useI18n();
  const capabilities = getCapabilities(backendConfig);

  if (capabilities.length === 0) {
    return <div className="py-8 text-center text-xs font-bold uppercase text-neutral-500">{emptyMessage ?? t('config.toolsEmpty')}</div>;
  }

  const toggleTool = (tool: string): void => {
    onChange(toggleToolSelection(selected, tool));
  };

  const toggleCapability = (tools: string[]): void => {
    onChange(toggleCapabilitySelection(selected, tools));
  };

  return (
    <div className="flex flex-col bg-neutral-50 dark:bg-zinc-900">
      {capabilities.map(capability => {
        const toolIds = capability.tools.map(tool => tool.id);
        const allSelected = toolIds.every(tool => selected.includes(tool));
        const someSelected = toolIds.some(tool => selected.includes(tool));
        return (
          <section key={capability.id} aria-label={t('config.toolCatalog.capabilityAria', { name: capability.label })}>
            <button
              type="button"
              onClick={() => toggleCapability(toolIds)}
              className="flex w-full items-start gap-2 border-b border-brutal-black/20 bg-neutral-100 px-3 py-2 text-left hover:bg-neutral-200 dark:bg-zinc-800 dark:hover:bg-zinc-700"
            >
              <span className={`mt-0.5 flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center border-2 border-brutal-black ${allSelected ? 'bg-brutal-black' : someSelected ? 'bg-brutal-black/40' : 'bg-white dark:bg-zinc-900'}`}>
                {allSelected && <svg className="h-2.5 w-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                {someSelected && !allSelected && <span className="h-1.5 w-1.5 bg-white" />}
              </span>
              <span className="min-w-0">
                <span className="block text-[10px] font-black uppercase tracking-widest text-neutral-600 dark:text-neutral-300">{capability.label}</span>
                {capability.description && <span className="mt-0.5 block text-[10px] font-medium leading-snug text-neutral-500 dark:text-neutral-400">{capability.description}</span>}
              </span>
            </button>
            <div className={`flex flex-col gap-1.5 ${compact ? 'p-1.5 pl-3' : 'p-2 pl-4'}`}>
              {capability.tools.map(tool => {
                const active = selected.includes(tool.id);
                const aiActive = activatedByAI.has(tool.id) && !active;
                return (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => toggleTool(tool.id)}
                    className={`flex w-full items-start gap-2.5 border-2 px-2.5 py-2 text-left shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] transition-all ${active ? 'border-brutal-black bg-brutal-green text-brutal-black' : aiActive ? 'border-brutal-black bg-brutal-yellow text-brutal-black' : 'border-brutal-black bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700'}`}
                  >
                    <span className={`mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center border-2 border-brutal-black ${(active || aiActive) ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}>
                      {active && <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                      {aiActive && <span className="text-[7px] font-black leading-none text-white">AI</span>}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] font-black uppercase leading-tight">{tool.name}</span>
                        {tool.requiresApproval && <span className="border border-current px-1 py-px text-[8px] font-bold uppercase opacity-70">{t('config.toolCatalog.approval')}</span>}
                      </span>
                      {tool.description && <span className="mt-1 block text-[10px] font-medium normal-case leading-snug opacity-75">{tool.description}</span>}
                      {tool.runtimeName && <span className="mt-1 block font-mono text-[9px] normal-case opacity-50">{tool.runtimeName}</span>}
                    </span>
                    {aiActive && onDeactivate && (
                      <span
                        role="button"
                        tabIndex={0}
                        title={t('config.toolCatalog.deactivate')}
                        onClick={event => { event.stopPropagation(); onDeactivate(tool.id); }}
                        onKeyDown={event => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.stopPropagation();
                            onDeactivate(tool.id);
                          }
                        }}
                        className="flex h-4 w-4 flex-shrink-0 cursor-pointer items-center justify-center hover:opacity-70"
                      >
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
