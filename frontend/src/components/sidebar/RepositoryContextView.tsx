import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowPathIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import { memoryApi } from '../../lib/memoryApi';
import type { RepositoryContextResponse, RepositoryInstruction } from '../../types/memory';
import { BrutalButton } from '../BrutalButton';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { CoreMemoryBlock } from '../memory/CoreMemoryBlock';

interface RepositoryContextViewProps {
  chatId: string;
}

function InstructionCard({ instruction }: { instruction: RepositoryInstruction }) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(true);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(instruction.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
      <header className="flex items-start justify-between gap-2 border-b-2 border-brutal-black px-3 py-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-brutal text-sm uppercase text-brutal-black dark:text-white">
              {instruction.name}
            </h3>
            <span className="border border-brutal-black px-1 font-mono text-[9px] uppercase dark:border-white">
              {t(`repositoryContext.sources.${instruction.source}`)}
            </span>
          </div>
          <p
            className="mt-1 truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-400"
            title={instruction.path}
          >
            {instruction.path}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <BrutalButton size="xs" onClick={copy} disabled={!instruction.content}>
            {copied ? t('coreMemory.copiedText') : t('common.copy')}
          </BrutalButton>
          <BrutalButton
            size="icon"
            onClick={() => setCollapsed((value) => !value)}
            aria-expanded={!collapsed}
            title={collapsed ? t('memoryView.expandSection') : t('memoryView.collapseSection')}
          >
            <ChevronDownIcon
              className={`h-4 w-4 stroke-2 transition-transform ${collapsed ? '-rotate-90' : ''}`}
            />
          </BrutalButton>
        </div>
      </header>
      {!collapsed && instruction.content && (
        <div className="max-h-[420px] overflow-y-auto overflow-x-hidden break-words bg-neutral-50 px-3 py-2 text-sm leading-6 dark:bg-zinc-900 [&_h1]:mb-1 [&_h1]:mt-3 [&_h2]:mb-1 [&_h2]:mt-3 [&_li]:my-0 [&_ol]:my-1 [&_p]:my-1 [&_ul]:my-1">
          <MarkdownRenderer content={instruction.content} streamingLite />
        </div>
      )}
    </section>
  );
}

export function RepositoryContextView({ chatId }: RepositoryContextViewProps) {
  const { t } = useI18n();
  const { isStreaming } = useChatStreamingStore();
  const previousStreaming = useRef(isStreaming);
  const [data, setData] = useState<RepositoryContextResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await memoryApi.getRepositoryContext(chatId));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t('repositoryContext.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [chatId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (previousStreaming.current && !isStreaming) void load();
    previousStreaming.current = isStreaming;
  }, [isStreaming, load]);

  const updateProjectContext = async (_label: string, content: string) => {
    const projectId = data?.project.projectId;
    if (!projectId) return;
    await memoryApi.updateProjectContext(projectId, content);
    setData((current) =>
      current
        ? {
            ...current,
            project: { ...current.project, content, exists: true },
          }
        : current
    );
  };

  const hasProjectContext = Boolean(data?.project.content.trim());
  const hasInstructions = Boolean(data?.instructions.length);

  return (
    <div className="flex h-full min-h-0 flex-col bg-neutral-50 dark:bg-zinc-900">
      <header className="flex items-center justify-between border-b-3 border-brutal-black bg-white px-3 py-3 dark:bg-zinc-800">
        <div className="min-w-0">
          <h2 className="font-brutal text-base uppercase text-brutal-black dark:text-white">
            {t('repositoryContext.title')}
          </h2>
          <p className="truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
            {t('repositoryContext.description')}
          </p>
        </div>
        <BrutalButton
          size="icon"
          onClick={() => void load()}
          disabled={loading}
          title={t('common.refresh')}
        >
          <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </BrutalButton>
      </header>

      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-3">
        {error && (
          <div className="border-2 border-brutal-red bg-white p-3 font-mono text-xs text-brutal-red dark:bg-zinc-800">
            {error}
          </div>
        )}

        {loading && !data && (
          <div className="border-2 border-brutal-black bg-white p-4 font-mono text-xs uppercase animate-brutal-blink dark:bg-zinc-800">
            {t('common.loading')}
          </div>
        )}

        {data && hasProjectContext && (
          <section className="space-y-2">
            <h3 className="border-b-2 border-brutal-black pb-1 font-brutal text-xs uppercase dark:border-white">
              {t('repositoryContext.projectContext')}
            </h3>
            <div title={data.project.path}>
              <CoreMemoryBlock
                label="context"
                content={data.project.content}
                titleOverride="context.md"
                descriptionOverride={data.project.projectName}
                collapsible
                onUpdate={updateProjectContext}
              />
            </div>
          </section>
        )}

        {data && hasInstructions && (
          <section className="space-y-2">
            <div className="border-b-2 border-brutal-black pb-1 dark:border-white">
              <h3 className="font-brutal text-xs uppercase">
                {t('repositoryContext.repositoryInstructions')}
              </h3>
              <p className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                {t('repositoryContext.repositoryInstructionsDesc')}
              </p>
            </div>
            {data.instructions.map((instruction) => (
              <InstructionCard key={instruction.path} instruction={instruction} />
            ))}
          </section>
        )}

        {data && !hasProjectContext && !hasInstructions && (
          <div className="border-2 border-dashed border-neutral-400 px-4 py-8 text-center font-mono text-xs text-neutral-500 dark:border-zinc-600 dark:text-neutral-400">
            {t('repositoryContext.empty')}
          </div>
        )}
      </div>
    </div>
  );
}
