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

  return [];
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

export function resolveCatalogText(
  translate: (key: string) => string,
  key: string,
  fallback: string,
): string {
  const value = translate(key);
  return value === key ? fallback : value;
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
  const translated = (key: string, fallback: string): string =>
    resolveCatalogText(t, key, fallback);

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
        const capabilityName = translated(
          `config.toolCatalog.capabilities.${capability.id}.name`,
          capability.label,
        );
        const capabilityDescription = translated(
          `config.toolCatalog.capabilities.${capability.id}.description`,
          capability.description,
        );
        return (
          <section key={capability.id} aria-label={t('config.toolCatalog.capabilityAria', { name: capabilityName })}>
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
                <span className="block text-[10px] font-black uppercase tracking-widest text-neutral-600 dark:text-neutral-300">{capabilityName}</span>
                {capabilityDescription && <span className="mt-0.5 block text-[10px] font-medium leading-snug text-neutral-500 dark:text-neutral-400">{capabilityDescription}</span>}
              </span>
            </button>
            <div className={`flex flex-col gap-1.5 ${compact ? 'p-1.5 pl-3' : 'p-2 pl-4'}`}>
              {capability.tools.map(tool => {
                const active = selected.includes(tool.id);
                const aiActive = activatedByAI.has(tool.id) && !active;
                const toolName = translated(
                  `config.toolCatalog.tools.${tool.id}.name`,
                  tool.name,
                );
                const toolDescription = translated(
                  `config.toolCatalog.tools.${tool.id}.description`,
                  tool.description,
                );
                return (
                  <div
                    key={tool.id}
                    className={`flex w-full border-2 text-left shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] transition-all ${active ? 'border-brutal-black bg-brutal-green text-brutal-black' : aiActive ? 'border-brutal-black bg-brutal-yellow text-brutal-black' : 'border-brutal-black bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700'}`}
                  >
                    <button
                      type="button"
                      onClick={() => toggleTool(tool.id)}
                      className="flex min-w-0 flex-1 items-start gap-2.5 bg-transparent px-2.5 py-2 text-left"
                    >
                      <span className={`mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center border-2 border-brutal-black ${(active || aiActive) ? 'bg-brutal-black' : 'bg-white dark:bg-zinc-900'}`}>
                        {active && <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                        {aiActive && <span className="text-[7px] font-black leading-none text-white">AI</span>}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="text-[11px] font-black uppercase leading-tight">{toolName}</span>
                          {tool.requiresApproval && <span className="border border-current px-1 py-px text-[8px] font-bold uppercase opacity-70">{t('config.toolCatalog.approval')}</span>}
                        </span>
                        {toolDescription && <span className="mt-1 block text-[10px] font-medium normal-case leading-snug opacity-75">{toolDescription}</span>}
                        {tool.runtimeName && <span className="mt-1 block font-mono text-[9px] normal-case opacity-50">{tool.runtimeName}</span>}
                      </span>
                    </button>
                    {aiActive && onDeactivate && (
                      <button
                        type="button"
                        title={t('config.toolCatalog.deactivate')}
                        aria-label={t('config.toolCatalog.deactivateTool', { name: toolName })}
                        onClick={() => onDeactivate(tool.id)}
                        className="flex w-8 flex-shrink-0 items-center justify-center border-l-2 border-brutal-black hover:bg-black/10"
                      >
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
