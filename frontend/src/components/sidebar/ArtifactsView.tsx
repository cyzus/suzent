import React, { useState } from 'react';
import {
  ArrowTopRightOnSquareIcon,
  DocumentTextIcon,
  MusicalNoteIcon,
  PhotoIcon,
  VideoCameraIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { useChatStore } from '../../hooks/useChatStore';
import { getApiBase, getSandboxParams } from '../../lib/api';
import type { ChatArtifact } from '../../lib/chatArtifacts';
import { ImageViewer } from '../ImageViewer';
import { ArtifactCover } from '../artifacts/ArtifactCard';

export type OpenArtifact = (path: string, name: string) => void;

function useServeUrl(): (path: string) => string {
  const { currentChatId, config } = useChatStore();
  return (path) =>
    `${getApiBase()}/sandbox/serve?${getSandboxParams(currentChatId || '', path, config.sandbox_volumes)}`;
}

export const ARTIFACT_KIND_ICONS = {
  image: PhotoIcon,
  video: VideoCameraIcon,
  audio: MusicalNoteIcon,
  file: DocumentTextIcon,
} as const;

const Thumbnail: React.FC<{ artifact: ChatArtifact; src: string; onOpen: () => void }> = ({
  artifact,
  src,
  onOpen,
}) => (
  <button
    type="button"
    onClick={onOpen}
    title={artifact.displayPath}
    className="group relative aspect-square overflow-hidden border border-neutral-200 bg-neutral-100 cursor-zoom-in focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-500 dark:border-zinc-700 dark:bg-zinc-800"
  >
    <ArtifactCover kind="image" name={artifact.name} src={src} />
  </button>
);

const ArtifactRow: React.FC<{
  artifact: ChatArtifact;
  onOpen: OpenArtifact;
  children?: React.ReactNode;
}> = ({ artifact, onOpen, children }) => {
  const { t } = useI18n();
  const Icon = ARTIFACT_KIND_ICONS[artifact.kind];
  const directory = artifact.displayPath.slice(0, artifact.displayPath.lastIndexOf('/') + 1);
  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={() => onOpen(artifact.path, artifact.name)}
        title={artifact.displayPath}
        aria-label={t('artifacts.openInFiles', { file: artifact.name })}
        className="flex w-full min-w-0 items-center gap-2 px-2 py-1.5 text-left transition-colors hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-500 dark:hover:bg-white/[0.04]"
      >
        <Icon className="h-4 w-4 shrink-0 text-neutral-400 dark:text-neutral-500" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-xs font-semibold leading-5 text-neutral-800 dark:text-neutral-200">
            {artifact.name}
          </span>
          {directory && (
            <span className="block truncate font-mono text-[10px] leading-4 text-neutral-500 dark:text-neutral-400">
              {directory}
            </span>
          )}
        </span>
        <ArrowTopRightOnSquareIcon
          className="h-3.5 w-3.5 shrink-0 text-neutral-400"
          aria-hidden="true"
        />
      </button>
      {children}
    </li>
  );
};

interface ArtifactsViewProps {
  artifacts: ChatArtifact[];
  onOpen: OpenArtifact;
}

/** Everything the agent produced in this conversation: media first, then written files. */
export const ArtifactsView: React.FC<ArtifactsViewProps> = ({ artifacts, onOpen }) => {
  const { t } = useI18n();
  const serveUrl = useServeUrl();
  const [viewing, setViewing] = useState<string | null>(null);
  const images = artifacts.filter((artifact) => artifact.kind === 'image');
  const players = artifacts.filter(
    (artifact) => artifact.kind === 'video' || artifact.kind === 'audio'
  );
  const files = artifacts.filter((artifact) => artifact.kind === 'file');
  const imageUrls = images.map((artifact) => serveUrl(artifact.path));

  if (artifacts.length === 0) {
    return (
      <p className="px-5 py-4 text-xs text-neutral-400 dark:text-neutral-500">
        {t('artifacts.empty')}
      </p>
    );
  }

  const heading = (label: string, count: number): React.ReactNode => (
    <h3 className="flex items-center gap-1.5 px-2 pb-1.5 text-[11px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
      {label}
      <span className="font-mono tabular-nums text-neutral-400">{count}</span>
    </h3>
  );

  return (
    <div className="flex flex-col gap-5 px-2 py-3">
      {images.length > 0 && (
        <section>
          {heading(t('artifacts.images'), images.length)}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-1.5 px-2">
            {images.map((artifact, index) => (
              <Thumbnail
                key={artifact.path}
                artifact={artifact}
                src={imageUrls[index]}
                onOpen={() => setViewing(imageUrls[index])}
              />
            ))}
          </div>
        </section>
      )}
      {players.length > 0 && (
        <section>
          {heading(t('artifacts.media'), players.length)}
          <ul className="flex flex-col gap-2">
            {players.map((artifact) => (
              <ArtifactRow key={artifact.path} artifact={artifact} onOpen={onOpen}>
                {artifact.kind === 'video' ? (
                  <video
                    src={serveUrl(artifact.path)}
                    controls
                    playsInline
                    preload="metadata"
                    className="mx-2 mt-1 max-h-60 w-[calc(100%-1rem)] bg-black"
                  />
                ) : (
                  <audio
                    src={serveUrl(artifact.path)}
                    controls
                    preload="metadata"
                    className="mx-2 mt-1 w-[calc(100%-1rem)]"
                  />
                )}
              </ArtifactRow>
            ))}
          </ul>
        </section>
      )}
      {files.length > 0 && (
        <section>
          {heading(t('artifacts.files'), files.length)}
          <ul className="flex flex-col">
            {files.map((artifact) => (
              <ArtifactRow key={artifact.path} artifact={artifact} onOpen={onOpen} />
            ))}
          </ul>
        </section>
      )}
      <ImageViewer
        src={viewing}
        images={imageUrls}
        onNavigate={setViewing}
        onClose={() => setViewing(null)}
      />
    </div>
  );
};

/** A row of the newest image thumbnails, or the newest file names, for the overview. */
export const ArtifactsPreview: React.FC<{ artifacts: ChatArtifact[] }> = ({ artifacts }) => {
  const serveUrl = useServeUrl();
  const images = artifacts.filter((artifact) => artifact.kind === 'image').slice(0, 4);
  if (images.length > 0) {
    return (
      <div className="mt-1.5 flex gap-1">
        {images.map((artifact) => (
          <img
            key={artifact.path}
            src={serveUrl(artifact.path)}
            alt={artifact.name}
            loading="lazy"
            className="h-10 w-10 shrink-0 border border-neutral-200 object-cover dark:border-zinc-700"
          />
        ))}
      </div>
    );
  }
  return (
    <ul className="mt-1.5 space-y-0.5">
      {artifacts.slice(0, 2).map((artifact) => (
        <li
          key={artifact.path}
          className="truncate font-mono text-xs text-neutral-500 dark:text-neutral-400"
        >
          {artifact.name}
        </li>
      ))}
    </ul>
  );
};
