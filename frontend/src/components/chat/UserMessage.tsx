import React from 'react';
import type { Message } from '../../types/api';

interface UserMessageProps {
  message: Message;
}

export const UserMessage: React.FC<UserMessageProps> = ({ message }) => {
  // Don't render empty messages (no content and no images)
  if (!message.content?.trim() && (!message.images || message.images.length === 0)) {
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
              />
              <div className="absolute bottom-0 left-0 right-0 bg-brutal-black text-brutal-white text-xs px-2 py-1 font-bold opacity-0 group-hover:opacity-100 transition-opacity duration-100">
                {img.filename}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Text content */}
      {message.content && (
        <div className="flex justify-end">
          <div className="bg-brutal-yellow border-3 border-brutal-black shadow-brutal-lg px-5 py-4 max-w-full font-medium relative select-text">
            <div className="prose prose-sm max-w-none break-words text-brutal-black font-sans">
              {message.content}
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
