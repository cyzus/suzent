import { useSidebarExpansion } from './SidebarExpansionContext';
import React, { useMemo } from 'react';
import { MarkdownRenderer, CodeBlock, MermaidDiagram } from '../';
import {
  isImageFile,
  isPdfFile,
  isVideoFile,
  isAudioFile,
  isHtmlFile,
  isMarkdownFile,
  isMermaidFile,
  getLanguageForFile,
} from '../../lib/fileUtils';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';

interface FilePreviewProps {
  filename: string;
  content: string | null;
  chatId: string;
  path: string;
  inheritChatVolumes?: boolean;
}

export const FilePreview: React.FC<FilePreviewProps> = ({
  filename,
  content,
  chatId,
  path,
  inheritChatVolumes = true,
}) => {
  const { config } = useChatStore();
  const volumes = inheritChatVolumes ? config.sandbox_volumes : undefined;
  const expanded = useSidebarExpansion()?.expanded ?? false;

  // Construct raw serve URL
  // Use the wildcard route to ensure relative paths in HTML/CSS/JS work correctly
  const serveUrl = useMemo(() => {
    // Remove leading slash for clean URL construction
    const cleanPath = path.startsWith('/') ? path.slice(1) : path;

    // Get volume params only (empty chat_id/path as they are in the route)
    const params = getSandboxParams('', '', volumes);
    const queryPart = params ? `?${params}` : '';

    return `${getApiBase()}/sandbox/serve/${chatId}/${cleanPath}${queryPart}`;
  }, [chatId, path, volumes]);

  // 1. Images
  if (isImageFile(filename)) {
    return (
      <div className="flex items-center justify-center p-8 bg-neutral-50 dark:bg-zinc-900/50 h-full w-full">
        <img
          src={serveUrl}
          alt={filename}
          className={
            expanded
              ? 'max-w-full max-h-full object-contain'
              : 'max-w-full max-h-full object-contain drop-shadow-md rounded-sm'
          }
        />
      </div>
    );
  }

  if (isVideoFile(filename)) {
    return (
      <div className="flex items-center justify-center p-4 bg-black h-full w-full">
        <video
          key={serveUrl}
          src={serveUrl}
          controls
          playsInline
          preload="metadata"
          className="max-w-full max-h-full"
        />
      </div>
    );
  }

  if (isAudioFile(filename)) {
    return (
      <div className="flex items-center justify-center p-6 bg-neutral-50 dark:bg-zinc-900/50 h-full w-full">
        <audio
          key={serveUrl}
          src={serveUrl}
          controls
          preload="metadata"
          className="w-full max-w-md"
        />
      </div>
    );
  }

  // 2. PDF
  if (isPdfFile(filename)) {
    return (
      <iframe src={serveUrl} className="w-full h-full border-none bg-white" title={filename} />
    );
  }

  // 3. HTML
  if (isHtmlFile(filename)) {
    return (
      <iframe
        src={serveUrl}
        className="w-full h-full border-none bg-white"
        title={filename}
        sandbox="allow-scripts allow-same-origin"
      />
    );
  }

  // 4. Markdown
  if (isMarkdownFile(filename)) {
    return (
      <div
        className={
          expanded
            ? 'file-document mx-auto w-full max-w-[88ch] px-5 py-6 sm:px-8 sm:py-8'
            : 'prose prose-sm max-w-none p-2'
        }
      >
        <MarkdownRenderer content={content || ''} />
      </div>
    );
  }

  // 5. Mermaid
  if (isMermaidFile(filename)) {
    return (
      <div className="p-2 overflow-auto h-full">
        <MermaidDiagram code={content || ''} />
      </div>
    );
  }

  // 6. Text / Code - Default fallback
  return (
    <div
      className={
        expanded
          ? 'p-3 h-full overflow-auto bg-white dark:bg-zinc-900'
          : 'p-0 h-full overflow-auto bg-white'
      }
    >
      <CodeBlock language={getLanguageForFile(filename)} code={content || ''} />
    </div>
  );
};
