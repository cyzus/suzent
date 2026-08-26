import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowPathIcon,
  CheckIcon,
  ChevronDownIcon,
  ClipboardDocumentIcon,
  PencilIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import { memoryApi } from '../../lib/memoryApi';
import type { RepositoryContextResponse, RepositoryInstruction } from '../../types/memory';
import { BrutalIconButton } from '../BrutalButton';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';

interface RepositoryContextViewProps {
  chatId: string;
}

interface ContextFileCardProps {
  name: string;
  content: string;
  sourceLabel: string;
  path: string;
  editable?: boolean;
  onSave?: (content: string) => Promise<void>;
}

function ContextFileCard({
  name,
  content,
  sourceLabel,
  path,
  editable = false,
  onSave,
}: ContextFileCardProps) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setDraft(content);
  }, [content]);

  const copy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  const save = async () => {
    if (!onSave || draft === content) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const cancel = () => {
    setDraft(content);
    setEditing(false);
  };

  return (
    <article className="border-2 border-brutal-black bg-white shadow-[3px_3px_0_0_#000] dark:bg-zinc-800">
      <div className="flex items-start gap-2 px-3 py-2.5">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="min-w-0 flex-1 text-left"
          aria-expanded={expanded}
        >
          <div className="flex min-w-0 items-center gap-2">
            <ChevronDownIcon
              className={`h-4 w-4 shrink-0 stroke-[2.5] transition-transform ${expanded ? '' : '-rotate-90'}`}
            />
            <span className="truncate font-brutal text-sm uppercase leading-none text-brutal-black dark:text-white">
              {name}
            </span>
            <span className="shrink-0 border border-brutal-black px-1.5 py-0.5 font-mono text-[8px] uppercase leading-none text-neutral-600 dark:border-white dark:text-neutral-300">
              {sourceLabel}
            </span>
          </div>
          <p
            className="ml-6 mt-1.5 truncate font-mono text-[10px] leading-none text-neutral-500 dark:text-neutral-400"
            title={path}
          >
            {path}
          </p>
        </button>

        {expanded && !editing && (
          <div className="flex shrink-0 gap-1.5">
            <BrutalIconButton
              label={copied ? t('coreMemory.copiedText') : t('common.copy')}
              onClick={copy}
            >
              {copied ? (
                <CheckIcon className="h-4 w-4 stroke-[2.5]" />
              ) : (
                <ClipboardDocumentIcon className="h-4 w-4 stroke-2" />
              )}
            </BrutalIconButton>
            {editable && (
              <BrutalIconButton label={t('common.edit')} onClick={() => setEditing(true)}>
                <PencilIcon className="h-4 w-4 stroke-2" />
              </BrutalIconButton>
            )}
          </div>
        )}
      </div>

      {expanded && (
        <div className="border-t-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900">
          {editing ? (
            <div className="space-y-2 p-2.5">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="min-h-56 w-full resize-y border-2 border-brutal-black bg-white p-2.5 font-mono text-xs leading-5 text-brutal-black focus:outline-none focus:ring-2 focus:ring-brutal-black dark:bg-zinc-800 dark:text-white"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <BrutalIconButton label={t('common.cancel')} onClick={cancel} disabled={saving}>
                  <XMarkIcon className="h-4 w-4 stroke-[2.5]" />
                </BrutalIconButton>
                <BrutalIconButton
                  label={saving ? t('common.saving') : t('common.save')}
                  onClick={() => void save()}
                  disabled={saving || draft === content}
                >
                  <CheckIcon className="h-4 w-4 stroke-[2.5]" />
                </BrutalIconButton>
              </div>
            </div>
          ) : (
            <div className="break-words px-3 py-2.5 text-[13px] leading-5 text-slate-700 dark:text-zinc-200 [&_blockquote]:my-2 [&_li]:my-0 [&_ol]:my-1.5 [&_p]:my-1.5 [&_pre]:my-2 [&_ul]:my-1.5">
              <MarkdownRenderer content={content} streamingLite compact />
            </div>
          )}
        </div>
      )}
    </article>
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

  const updateProjectContext = async (content: string) => {
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
    <div className="flex h-full min-h-0 flex-col bg-neutral-100 dark:bg-zinc-900">
      <header className="flex items-center gap-3 border-b-3 border-brutal-black bg-white px-3 py-2.5 dark:bg-zinc-800">
        <div className="min-w-0 flex-1">
          <h2 className="font-brutal text-base uppercase leading-none text-brutal-black dark:text-white">
            {t('repositoryContext.title')}
          </h2>
          <p className="mt-1 truncate font-mono text-[10px] leading-none text-neutral-500 dark:text-neutral-400">
            {data?.project.projectName || t('repositoryContext.description')}
          </p>
        </div>
        <BrutalIconButton
          label={t('common.refresh')}
          onClick={() => void load()}
          disabled={loading}
        >
          <ArrowPathIcon className={`h-4 w-4 stroke-2 ${loading ? 'animate-spin' : ''}`} />
        </BrutalIconButton>
      </header>

      <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto overflow-x-hidden p-3">
        {error && (
          <div className="border-2 border-brutal-red bg-white p-3 font-mono text-xs text-brutal-red dark:bg-zinc-800">
            {error}
          </div>
        )}

        {loading && !data && (
          <div className="border-2 border-brutal-black bg-white p-3 font-mono text-[10px] uppercase animate-brutal-blink dark:bg-zinc-800">
            {t('common.loading')}
          </div>
        )}

        {data && hasProjectContext && (
          <section className="space-y-2">
            <h3 className="font-brutal text-[11px] uppercase tracking-wide text-neutral-600 dark:text-neutral-300">
              {t('repositoryContext.projectContext')}
            </h3>
            <ContextFileCard
              name="context.md"
              content={data.project.content}
              sourceLabel={t('repositoryContext.projectMemory')}
              path={data.project.path}
              editable
              onSave={updateProjectContext}
            />
          </section>
        )}

        {data && hasInstructions && (
          <section className="space-y-2">
            <div>
              <h3 className="font-brutal text-[11px] uppercase tracking-wide text-neutral-600 dark:text-neutral-300">
                {t('repositoryContext.repositoryInstructions')}
              </h3>
              <p className="mt-1 font-mono text-[9px] leading-3 text-neutral-500 dark:text-neutral-400">
                {t('repositoryContext.repositoryInstructionsDesc')}
              </p>
            </div>
            {data.instructions.map((instruction: RepositoryInstruction) => (
              <ContextFileCard
                key={instruction.path}
                name={instruction.name}
                content={instruction.content}
                sourceLabel={t(`repositoryContext.sources.${instruction.source}`)}
                path={instruction.path}
              />
            ))}
          </section>
        )}

        {data && !hasProjectContext && !hasInstructions && (
          <div className="border-2 border-dashed border-neutral-400 bg-white px-4 py-8 text-center font-mono text-xs text-neutral-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-neutral-400">
            {t('repositoryContext.empty')}
          </div>
        )}
      </div>
    </div>
  );
}
