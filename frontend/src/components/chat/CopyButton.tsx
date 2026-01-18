import React, { useState } from 'react';
import { useStatusStore } from '../../hooks/useStatusStore';

interface CopyButtonProps {
  text: string;
  className?: string;
  statusMessage?: string;
}

export const CopyButton: React.FC<CopyButtonProps> = ({
  text,
  className,
  statusMessage = 'COPIED_TO_CLIPBOARD'
}) => {
  const { setStatus } = useStatusStore();
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setStatus(statusMessage, 'success');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className={`w-8 h-8 flex items-center justify-center bg-transparent rounded hover:bg-neutral-100 transition-colors text-neutral-400 hover:text-brutal-black ${className || 'absolute top-2 right-2'}`}
      title="Copy to clipboard"
      type="button"
    >
      {copied ? (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <rect x="8" y="8" width="12" height="12" rx="2" ry="2" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2" />
        </svg>
      )}
    </button>
  );
};
