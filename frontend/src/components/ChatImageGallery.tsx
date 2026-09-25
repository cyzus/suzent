import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ImageViewer } from './ImageViewer';

type Entry = { node: HTMLElement; sources: string[] };
export function collectChatImages(entries: Iterable<Entry>, src: string): string[] {
  const ordered = [...entries]
    .filter((entry) => entry.node.isConnected)
    .sort((a, b) =>
      a.node.compareDocumentPosition(b.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
    );
  const images = [...new Set(ordered.flatMap((entry) => entry.sources))];
  if (!images.includes(src)) images.push(src);
  return images;
}

const GalleryContext = createContext<{
  register: (entry: Entry) => () => void;
  open: (src: string) => void;
} | null>(null);

export const ChatImageGallery: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const entries = useRef(new Set<Entry>());
  const [selection, setSelection] = useState<{ src: string; images: string[] } | null>(null);
  const register = useCallback((entry: Entry) => {
    entries.current.add(entry);
    return () => {
      entries.current.delete(entry);
    };
  }, []);
  const open = useCallback((src: string) => {
    const images = collectChatImages(entries.current, src);
    setSelection({ src, images });
  }, []);
  return (
    <GalleryContext.Provider value={{ register, open }}>
      {children}
      <ImageViewer
        src={selection?.src ?? null}
        images={selection?.images}
        onNavigate={(src) => setSelection((current) => (current ? { ...current, src } : null))}
        onClose={() => setSelection(null)}
      />
    </GalleryContext.Provider>
  );
};

export function useChatImages(sources: string[]) {
  const gallery = useContext(GalleryContext);
  const ref = useRef<HTMLDivElement>(null);
  const serialized = JSON.stringify(sources);
  useEffect(() => {
    if (!gallery || !ref.current) return;
    return gallery.register({ node: ref.current, sources: JSON.parse(serialized) });
  }, [gallery?.register, serialized]);
  return { ref, open: gallery?.open };
}

export const ChatMarkdownImage: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = (props) => {
  const { ref, open } = useChatImages(props.src ? [props.src] : []);
  return (
    <div ref={ref}>
      <button
        type="button"
        className="cursor-zoom-in"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          if (props.src) open?.(props.src);
        }}
      >
        <img {...props} />
      </button>
    </div>
  );
};
