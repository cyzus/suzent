import React, { useState } from 'react';
import { CheckIcon, DocumentDuplicateIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';

interface CopyButtonProps {
  text: string;
  className?: string;
}

export const CopyButton: React.FC<CopyButtonProps> = ({ text, className }) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className={`message-action-button ${className || 'absolute top-2 right-2'}`}
      title={t(copied ? 'status.copiedToClipboard' : 'status.copyToClipboard')}
      aria-label={t(copied ? 'status.copiedToClipboard' : 'status.copyToClipboard')}
      type="button"
    >
      {copied ? (
        <CheckIcon className="text-green-600 dark:text-green-400" aria-hidden="true" />
      ) : (
        <DocumentDuplicateIcon aria-hidden="true" />
      )}
    </button>
  );
};
