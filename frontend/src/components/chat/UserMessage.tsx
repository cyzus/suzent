import React from 'react';
import type { Message } from '../../types/api';
import { FileIcon } from '../FileIcon';
import { ClickableContent } from '../ClickableContent';
import { ArrowDownTrayIcon, EyeIcon } from '@heroicons/react/24/outline';
import { API_BASE, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';

interface UserMessageProps {
  message: Message;
  chatId?: string;
  onImageClick?: (src: string) => void;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}

export const UserMessage: React.FC<UserMessageProps> = ({ message, chatId, onImageClick, onFileClick }) => {
  const { config } = useChatStore();

  // Don't render empty messages (no content, no images, and no files)
  if (!message.content?.trim() &&
    (!message.images || message.images.length === 0) &&
    (!message.files || message.files.length === 0)) {
    return null;
  }

  return (
    <div className="w-full max-w-3xl space-y-3 pl-8 md:pl-16">
      {/* Images */}
      {message.images && message.images.length > 0 && (
        <div className="flex flex-wrap gap-3 justify-end">
          {message.images.map((img, imgIdx) => (
            <div key={imgIdx} className="relative group animate-brutal-pop">
              <img
                src={`data:${img.mime_type};base64,${img.data}`}
                alt={img.filename}
                className="max-w-sm max-h-64 border-4 border-brutal-black shadow-brutal-lg object-contain bg-white"
                title={img.filename}
                onClick={() => onImageClick?.(`data:${img.mime_type};base64,${img.data}`)}
                style={{ cursor: onImageClick ? 'pointer' : 'default' }}
              />
              <div className="absolute bottom-0 left-0 right-0 bg-brutal-black text-brutal-white text-xs px-2 py-1 font-bold opacity-0 group-hover:opacity-100 transition-opacity duration-100">
                {img.filename}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* File attachments */}
      {message.files && message.files.length > 0 && (
        <div className="flex flex-col gap-2 items-end">
          {message.files.map((file, fileIdx) => {
            // Generate download URL with volumes
            const downloadParams = getSandboxParams(chatId || '', file.path, config.sandbox_volumes);
            const downloadUrl = `${API_BASE}/sandbox/serve?${downloadParams}`;

            return (
              <div key={fileIdx} className="bg-white border-3 border-brutal-black shadow-brutal px-4 py-3 flex items-center gap-3 max-w-md w-full animate-brutal-pop">
                <FileIcon mimeType={file.mime_type} className="w-6 h-6 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-brutal-black truncate">{file.filename}</div>
                  <div className="text-xs text-neutral-500">
                    {(file.size / 1024).toFixed(1)} KB
                  </div>
                </div>
                {chatId && (
                  <div className="flex gap-2">
                    <button
                      onClick={(e) => onFileClick?.(file.path, file.filename, e.shiftKey)}
                      className="shrink-0 p-2 bg-brutal-yellow border-2 border-brutal-black text-brutal-black hover:translate-x-[1px] hover:translate-y-[1px] transition-all"
                      title="View file (Shift+Click for full screen)"
                    >
                      <EyeIcon className="w-4 h-4" />
                    </button>
                    <a
                      href={downloadUrl}
                      download={file.filename}
                      className="shrink-0 p-2 bg-brutal-blue border-2 border-brutal-black text-white hover:translate-x-[1px] hover:translate-y-[1px] transition-all"
                      title="Download file"
                    >
                      <ArrowDownTrayIcon className="w-4 h-4" />
                    </a>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Text content */}
      {message.content && (
        <div className="flex justify-end">
          <div className="bg-brutal-yellow border-3 border-brutal-black shadow-brutal-lg px-5 py-4 max-w-full font-medium relative select-text">
            <div className="prose prose-sm max-w-none break-words text-brutal-black font-sans whitespace-pre-wrap">
              <ClickableContent content={message.content} onFileClick={onFileClick} />
            </div>
          </div>
        </div>
      )}

      {/* User label */}
      <div className="text-[10px] font-bold text-neutral-400 uppercase text-right pr-1 opacity-0 group-hover/message:opacity-100 transition-opacity select-none">
        User
      </div>
    </div>
  );
};
