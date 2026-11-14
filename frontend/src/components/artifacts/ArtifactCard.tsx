import React, { useState } from 'react';
import {
  CheckIcon,
  ClipboardDocumentIcon,
  FolderOpenIcon,
  MusicalNoteIcon,
  PlayIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { getApiBase } from '../../lib/api';
import type { ChatArtifactKind } from '../../lib/chatArtifacts';
import { BrutalIconButton } from '../BrutalButton';
import presentation from '../../../../packages/presentation/tokens.json';

function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}

/** Shared with the phone apps: packages/presentation/tokens.json `fileCovers`. */
function fileCover(ext: string): string {
  return `var(--file-cover-${ext in presentation.fileCovers ? ext : 'default'})`;
}

const AUDIO_BARS = [40, 75, 55, 95, 65, 30, 80, 50, 70, 35, 60, 45];
const TEXT_LINES = [100, 85, 92, 60, 78];

interface CoverProps {
  kind: ChatArtifactKind;
  name: string;
  /** Where to load the picture from; null when the file can't be served. */
  src: string | null;
}

export const ArtifactCover: React.FC<CoverProps> = ({ kind, name, src }) => {
  const [failed, setFailed] = useState(!src);
  const ext = extension(name);

  if (kind === 'image' && !failed && src) {
    return (
      <img
        src={src}
        alt={name}
        loading="lazy"
        onError={() => setFailed(true)}
        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
      />
    );
  }
  if (kind === 'video' && !failed && src) {
    return (
      <>
        <video
          src={`${src}#t=0.1`}
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
  if (kind === 'audio') {
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
      className="relative flex h-full w-full items-center justify-center"
      style={{ backgroundColor: fileCover(ext) }}
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

export function revealArtifact(path: string, chatId?: string | null): void {
  void fetch(`${getApiBase()}/system/open_explorer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(chatId ? { path, chat_id: chatId } : { path }),
  });
}

/** Show in folder and copy location, as the artifact library offers them. */
export const ArtifactActions: React.FC<{
  path: string;
  /** Resolves a chat-relative path such as /workspace/x; library paths need none. */
  chatId?: string | null;
  copyable?: boolean;
}> = ({ path, chatId, copyable = true }) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const copyLocation = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <>
      <BrutalIconButton
        onClick={() => revealArtifact(path, chatId)}
        label={t('fileViewer.revealInExplorer')}
      >
        <FolderOpenIcon className="h-3.5 w-3.5 stroke-2" />
      </BrutalIconButton>
      {copyable && (
        <BrutalIconButton
          onClick={() => void copyLocation()}
          label={copied ? t('sandbox.locationCopied') : t('sandbox.copyLocation')}
        >
          {copied ? (
            <CheckIcon className="h-3.5 w-3.5 stroke-2" />
          ) : (
            <ClipboardDocumentIcon className="h-3.5 w-3.5 stroke-2" />
          )}
        </BrutalIconButton>
      )}
    </>
  );
};

/** A cover with the file's name under it; `children` is the line of detail below the name. */
export const ArtifactCard: React.FC<
  CoverProps & {
    title: string;
    onOpen: () => void;
    actions: React.ReactNode;
    children?: React.ReactNode;
  }
> = ({ kind, name, src, title, onOpen, actions, children }) => (
  <article className="group relative flex min-w-0 flex-col brutal-btn border-2 border-brutal-black bg-white dark:bg-zinc-800">
    <button
      type="button"
      onClick={onOpen}
      title={title}
      aria-label={name}
      className={`relative block aspect-[4/3] w-full overflow-hidden border-b-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900 ${kind === 'image' ? 'cursor-zoom-in' : ''}`}
    >
      <ArtifactCover kind={kind} name={name} src={src} />
    </button>
    <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
      {actions}
    </div>
    <div className="flex min-w-0 flex-1 flex-col gap-1 px-3 py-2.5">
      <button
        type="button"
        onClick={onOpen}
        title={name}
        className="truncate text-left font-mono text-xs font-bold text-brutal-black hover:underline dark:text-white"
      >
        {name}
      </button>
      {children && <div className="flex min-w-0 flex-col gap-0.5">{children}</div>}
    </div>
  </article>
);
