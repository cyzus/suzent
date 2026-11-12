import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChatBubbleLeftRightIcon,
  CheckIcon,
  ClipboardDocumentIcon,
  FolderOpenIcon,
  MagnifyingGlassIcon,
  MusicalNoteIcon,
  PlayIcon,
  RectangleStackIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { formatRelativeTime } from '../../lib/chatUtils';
import { isImeComposing } from '../../lib/ime';
import { BrutalIconButton } from '../BrutalButton';
import { BrutalSegmentedTabs } from '../BrutalSegmentedTabs';
import { RefreshButton } from '../RefreshButton';
import { FileViewer } from '../FileViewer';
import { ImageViewer } from '../ImageViewer';

type ArtifactKind = 'image' | 'video' | 'audio' | 'file';

interface IndexedArtifact {
  path: string;
  name: string;
  kind: ArtifactKind;
  project_id: string;
  chat_id: string | null;
  chat_title: string | null;
  serve_chat_id: string | null;
  modified: number;
  size: number;
}

interface ArtifactProject {
  id: string;
  name: string;
  count: number;
}

type KindFilter = 'all' | 'image' | 'media' | 'file';

const KIND_FILTERS: KindFilter[] = ['all', 'image', 'media', 'file'];

/** Cover colors for files without a picture, so a grid of documents still reads at a glance. */
const FILE_COVERS: Record<string, string> = {
  pdf: 'bg-[#FFD7D7] dark:bg-[#4A1D1D]',
  csv: 'bg-brutal-green dark:bg-[#1F3B1D]',
  xlsx: 'bg-brutal-green dark:bg-[#1F3B1D]',
  json: 'bg-[#D6E4FF] dark:bg-[#1B2A4A]',
  html: 'bg-[#D6E4FF] dark:bg-[#1B2A4A]',
  docx: 'bg-[#D6E4FF] dark:bg-[#1B2A4A]',
  pptx: 'bg-[#FFE0C2] dark:bg-[#4A2E1B]',
};

function matchesKind(filter: KindFilter, kind: ArtifactKind): boolean {
  if (filter === 'all') return true;
  if (filter === 'media') return kind === 'video' || kind === 'audio';
  return filter === kind;
}

function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}

function serveUrl(item: IndexedArtifact): string {
  return `${getApiBase()}/sandbox/serve?${getSandboxParams(item.serve_chat_id || '', item.path)}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const AUDIO_BARS = [40, 75, 55, 95, 65, 30, 80, 50, 70, 35, 60, 45];
const TEXT_LINES = [100, 85, 92, 60, 78];

const Cover: React.FC<{ item: IndexedArtifact }> = ({ item }) => {
  const [failed, setFailed] = useState(!item.serve_chat_id);
  const ext = extension(item.name);

  if (item.kind === 'image' && !failed) {
    return (
      <img
        src={serveUrl(item)}
        alt={item.name}
        loading="lazy"
        onError={() => setFailed(true)}
        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
      />
    );
  }
  if (item.kind === 'video' && !failed) {
    return (
      <>
        <video
          src={`${serveUrl(item)}#t=0.1`}
          muted
          playsInline
          preload="metadata"
          onError={() => setFailed(true)}
          className="h-full w-full bg-black object-cover"
        />
        <span className="absolute inset-0 m-auto flex h-11 w-11 items-center justify-center border-2 border-brutal-black bg-white text-brutal-black shadow-brutal-sm transition-transform group-hover:scale-110">
          <PlayIcon className="ml-0.5 h-5 w-5 stroke-[2.5]" />
        </span>
      </>
    );
  }
  if (item.kind === 'audio') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-brutal-yellow dark:bg-[#3A3410]">
        <MusicalNoteIcon className="h-8 w-8 stroke-2 text-brutal-black dark:text-brutal-yellow" />
        <div className="flex h-6 items-end gap-[3px]" aria-hidden="true">
          {AUDIO_BARS.map((height, index) => (
            <span
              key={index}
              style={{ height: `${height}%` }}
              className="w-1 bg-brutal-black/70 dark:bg-brutal-yellow/70"
            />
          ))}
        </div>
      </div>
    );
  }
  return (
    <div
      className={`relative flex h-full w-full items-center justify-center ${FILE_COVERS[ext] ?? 'bg-neutral-100 dark:bg-zinc-900'}`}
    >
      <div className="absolute inset-x-6 top-5 space-y-2 opacity-40" aria-hidden="true">
        {TEXT_LINES.map((width, index) => (
          <div
            key={index}
            style={{ width: `${width}%` }}
            className="h-1 bg-neutral-500 dark:bg-zinc-500"
          />
        ))}
      </div>
      <span className="relative border-2 border-brutal-black bg-white px-2.5 py-1 font-brutal text-lg uppercase tracking-tight text-brutal-black shadow-brutal-sm">
        {ext ? `.${ext}` : 'FILE'}
      </span>
    </div>
  );
};

interface ArtifactsPageProps {
  onOpenChat: (chatId: string) => void;
}

/** Everything the agent delivered, across projects. */
export const ArtifactsPage: React.FC<ArtifactsPageProps> = ({ onOpenChat }) => {
  const { t, locale } = useI18n();
  const [projects, setProjects] = useState<ArtifactProject[]>([]);
  const [items, setItems] = useState<IndexedArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [kind, setKind] = useState<KindFilter>('all');
  const [query, setQuery] = useState('');
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState<IndexedArtifact | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${getApiBase()}/artifacts`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as {
        projects: ArtifactProject[];
        items: IndexedArtifact[];
      };
      setProjects(data.projects);
      setItems(data.items);
    } catch {
      setError(t('artifactsPage.loadFailed'));
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const inProject = useMemo(
    () => items.filter((item) => !projectId || item.project_id === projectId),
    [items, projectId]
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return inProject.filter(
      (item) =>
        matchesKind(kind, item.kind) &&
        (!needle ||
          item.name.toLowerCase().includes(needle) ||
          (item.chat_title || '').toLowerCase().includes(needle))
    );
  }, [inProject, kind, query]);

  /** One section per project; items arrive newest first, so the most recent project leads. */
  const sections = useMemo(() => {
    const byProject = new Map<string, IndexedArtifact[]>();
    visible.forEach((item) => {
      byProject.set(item.project_id, [...(byProject.get(item.project_id) ?? []), item]);
    });
    return [...byProject.entries()].map(([id, sectionItems]) => ({
      id,
      name: projects.find((project) => project.id === id)?.name ?? '',
      items: sectionItems,
    }));
  }, [visible, projects]);

  const imageUrls = useMemo(
    () => visible.filter((item) => item.kind === 'image' && item.serve_chat_id).map(serveUrl),
    [visible]
  );

  const open = (item: IndexedArtifact): void => {
    if (!item.serve_chat_id) reveal(item);
    else if (item.kind === 'image') setViewingImage(serveUrl(item));
    else setPreviewing(item);
  };

  const reveal = (item: IndexedArtifact): void => {
    void fetch(`${getApiBase()}/system/open_explorer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: item.path }),
    });
  };

  const copyLocation = async (item: IndexedArtifact): Promise<void> => {
    try {
      await navigator.clipboard.writeText(item.path);
      setCopiedPath(item.path);
      window.setTimeout(
        () => setCopiedPath((current) => (current === item.path ? null : current)),
        1500
      );
    } catch {
      setCopiedPath(null);
    }
  };

  const kindCount = (filter: KindFilter): number =>
    inProject.filter((item) => matchesKind(filter, item.kind)).length;

  const kindLabel: Record<KindFilter, string> = {
    all: t('artifactsPage.kinds.all'),
    image: t('artifacts.images'),
    media: t('artifacts.media'),
    file: t('artifacts.files'),
  };

  const card = (item: IndexedArtifact): React.ReactNode => (
    <article
      key={item.path}
      className="group relative flex min-w-0 flex-col border-2 border-brutal-black bg-white shadow-brutal-sm transition-[transform,box-shadow] duration-150 hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal dark:bg-zinc-800"
    >
      <button
        type="button"
        onClick={() => open(item)}
        title={item.path}
        aria-label={item.name}
        className={`relative block aspect-[4/3] w-full overflow-hidden border-b-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900 ${item.kind === 'image' ? 'cursor-zoom-in' : ''}`}
      >
        <Cover item={item} />
      </button>
      <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <BrutalIconButton onClick={() => reveal(item)} label={t('fileViewer.revealInExplorer')}>
          <FolderOpenIcon className="h-3.5 w-3.5 stroke-2" />
        </BrutalIconButton>
        <BrutalIconButton
          onClick={() => void copyLocation(item)}
          label={copiedPath === item.path ? t('sandbox.locationCopied') : t('sandbox.copyLocation')}
        >
          {copiedPath === item.path ? (
            <CheckIcon className="h-3.5 w-3.5 stroke-2" />
          ) : (
            <ClipboardDocumentIcon className="h-3.5 w-3.5 stroke-2" />
          )}
        </BrutalIconButton>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1 px-3 py-2.5">
        <button
          type="button"
          onClick={() => open(item)}
          title={item.name}
          className="truncate text-left font-mono text-xs font-bold text-brutal-black hover:underline dark:text-white"
        >
          {item.name}
        </button>
        <div className="flex min-w-0 flex-col gap-0.5">
          {item.chat_id ? (
            <button
              type="button"
              onClick={() => onOpenChat(item.chat_id as string)}
              title={t('artifactsPage.openChat')}
              className="flex min-w-0 items-center gap-1 text-[11px] text-neutral-500 hover:text-brutal-black hover:underline dark:text-neutral-400 dark:hover:text-white"
            >
              <ChatBubbleLeftRightIcon className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span className="truncate">{item.chat_title || t('artifactsPage.untitledChat')}</span>
            </button>
          ) : (
            <span className="truncate text-[11px] text-neutral-400 dark:text-neutral-500">
              {t('artifactsPage.inLibrary')}
            </span>
          )}
          <span className="shrink-0 font-mono text-[10px] text-neutral-400">
            {formatRelativeTime(new Date(item.modified * 1000).toISOString(), locale)}
            {' · '}
            {formatSize(item.size)}
          </span>
        </div>
      </div>
    </article>
  );

  const projectRow = (id: string | null, label: string, count: number): React.ReactNode => {
    const selected = projectId === id;
    return (
      <button
        key={id ?? 'all'}
        type="button"
        aria-pressed={selected}
        onClick={() => setProjectId(id)}
        className={`flex shrink-0 items-center gap-3 border-2 px-3 py-2 text-left text-xs transition-colors md:w-full md:border-0 md:border-l-4 ${selected ? 'border-brutal-black bg-brutal-yellow font-bold text-brutal-black' : 'border-neutral-300 text-neutral-700 hover:bg-neutral-100 dark:border-zinc-600 dark:text-neutral-300 dark:hover:bg-zinc-700 md:border-transparent md:dark:border-transparent'}`}
      >
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <span
          className={`min-w-[1.75rem] border px-1 text-center font-mono text-[10px] tabular-nums ${selected ? 'border-brutal-black bg-white' : 'border-neutral-300 dark:border-zinc-600'}`}
        >
          {count}
        </span>
      </button>
    );
  };

  const visibleProjects = projects.filter((project) => project.count > 0);

  return (
    <div className="h-full w-full overflow-y-auto scrollbar-thin px-4 md:px-8 py-8 space-y-6 max-w-7xl mx-auto">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center border-2 border-brutal-black bg-brutal-yellow shadow-brutal-sm">
            <RectangleStackIcon className="h-6 w-6 stroke-2 text-brutal-black" />
          </span>
          <div>
            <h2 className="font-brutal text-2xl uppercase leading-none tracking-tighter">
              {t('artifactsPage.title')}
            </h2>
            <p className="mt-1 font-mono text-[11px] text-neutral-500 dark:text-neutral-400">
              {t('artifactsPage.summary', {
                count: items.length,
                projects: visibleProjects.length,
              })}
            </p>
          </div>
        </div>
        <div className="flex w-full items-center gap-2 sm:w-auto">
          <div className="relative flex-1 sm:flex-none">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (isImeComposing(event)) return;
                if (event.key === 'Escape') setQuery('');
              }}
              placeholder={t('artifactsPage.search')}
              aria-label={t('artifactsPage.search')}
              className="w-full border-2 border-brutal-black bg-white py-1.5 pl-8 pr-2 font-mono text-xs shadow-brutal-sm focus:outline-none focus:ring-2 focus:ring-brutal-yellow dark:bg-zinc-900 sm:w-64"
            />
          </div>
          <RefreshButton onClick={() => void load()} spinning={loading} />
        </div>
      </header>

      <BrutalSegmentedTabs
        tabs={KIND_FILTERS.map((filter) => ({
          id: filter,
          label: kindLabel[filter],
          trailing: (
            <span className="font-mono text-[10px] font-normal tabular-nums opacity-60">
              {kindCount(filter)}
            </span>
          ),
        }))}
        value={kind}
        onChange={setKind}
        containerClassName="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
        tabClassName="flex-1 gap-1.5 px-2 py-2.5 font-bold text-[11px] md:text-sm"
      />

      {error ? (
        <div className="border-2 border-brutal-red bg-white p-4 font-mono text-sm text-brutal-red shadow-brutal-sm dark:bg-zinc-800">
          {error}
        </div>
      ) : (
        <div className="flex flex-col gap-6 md:flex-row md:items-start">
          <nav
            aria-label={t('artifactsPage.projects')}
            className="md:sticky md:top-0 md:w-56 md:shrink-0 md:border-2 md:border-brutal-black md:bg-white md:shadow-brutal-sm md:dark:bg-zinc-800"
          >
            <h3 className="hidden border-b-2 border-brutal-black bg-neutral-100 px-3 py-2 font-brutal text-xs uppercase tracking-tight dark:bg-zinc-900 md:block">
              {t('artifactsPage.projects')}
            </h3>
            <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin md:flex-col md:gap-0.5 md:overflow-visible md:p-1.5">
              {projectRow(null, t('artifactsPage.allProjects'), items.length)}
              {visibleProjects.map((project) =>
                projectRow(project.id, project.name, project.count)
              )}
            </div>
          </nav>

          <div className="min-w-0 flex-1 space-y-8">
            {loaded && visible.length === 0 && (
              <div className="flex flex-col items-center border-2 border-dashed border-neutral-400 px-6 py-16 text-center dark:border-zinc-600">
                <span className="mb-4 flex h-14 w-14 items-center justify-center border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
                  <RectangleStackIcon className="h-7 w-7 stroke-2" />
                </span>
                <p className="font-brutal text-lg uppercase tracking-tight">
                  {items.length === 0 ? t('artifactsPage.empty') : t('artifactsPage.noMatches')}
                </p>
                {items.length === 0 && (
                  <p className="mt-2 max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
                    {t('artifactsPage.emptyHint')}
                  </p>
                )}
              </div>
            )}

            {sections.map((section) => (
              <section key={section.id} className="space-y-3">
                {!projectId && (
                  <div className="flex items-center gap-3">
                    <h3 className="font-brutal text-sm uppercase tracking-tight">{section.name}</h3>
                    <span className="h-0.5 flex-1 bg-brutal-black dark:bg-zinc-600" />
                    <span className="border-2 border-brutal-black bg-white px-1.5 font-mono text-[10px] dark:bg-zinc-800">
                      {section.items.length}
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(190px,1fr))] md:gap-5">
                  {section.items.map(card)}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}

      <ImageViewer
        src={viewingImage}
        images={imageUrls}
        onNavigate={setViewingImage}
        onClose={() => setViewingImage(null)}
      />
      <FileViewer
        filePath={previewing?.path ?? null}
        fileName={previewing?.name ?? null}
        chatId={previewing?.serve_chat_id ?? null}
        onClose={() => setPreviewing(null)}
        inheritChatVolumes={false}
      />
    </div>
  );
};
