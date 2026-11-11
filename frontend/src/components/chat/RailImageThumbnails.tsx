import React, { useState } from 'react';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { useChatImages } from '../ChatImageGallery';
import { ImageViewer } from '../ImageViewer';

export function RailImageThumbnails({ paths }: { paths: string[] }): React.ReactElement | null {
  const { currentChatId, config } = useChatStore();
  const urls = paths.map(
    (path) =>
      `${getApiBase()}/sandbox/serve?${getSandboxParams(currentChatId || '', path, config.sandbox_volumes)}`
  );
  const gallery = useChatImages(urls);
  const [selected, setSelected] = useState<string | null>(null);
  if (!currentChatId) return null;
  return (
    <div
      ref={gallery.ref}
      className="flex max-w-[45%] shrink-0 items-center gap-1.5 overflow-x-auto py-1"
    >
      {urls.map((src, index) => (
        <button
          key={src}
          type="button"
          title={paths[index]}
          onClick={() => (gallery.open ?? setSelected)(src)}
          className="h-10 w-14 shrink-0 cursor-zoom-in overflow-hidden rounded-sm border border-neutral-200 bg-neutral-100 transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue dark:border-zinc-700 dark:bg-zinc-900"
        >
          <img
            src={src}
            alt={paths[index].split(/[\\/]/).pop() || paths[index]}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        </button>
      ))}
      <ImageViewer
        src={selected}
        images={urls}
        onNavigate={setSelected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
