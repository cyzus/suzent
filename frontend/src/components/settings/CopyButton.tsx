import React, { useState } from 'react';
import { CheckIcon, ClipboardDocumentIcon } from '@heroicons/react/24/outline';
import { BrutalIconButton } from '../BrutalButton';

/** A small button that confirms it copied to the clipboard. */
export function CopyButton({
  value,
  tone = 'neutral',
  label = 'Copy',
}: {
  value: string;
  tone?: 'blue' | 'red' | 'neutral';
  label?: string;
}): React.ReactElement {
  const [copied, setCopied] = useState(false);
  return (
    <BrutalIconButton
      variant={tone === 'blue' ? 'primary' : tone === 'red' ? 'danger' : 'default'}
      disabled={!value}
      label={copied ? 'Copied' : label}
      onClick={() => {
        if (!value) return;
        navigator.clipboard?.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? (
        <CheckIcon className="h-4 w-4 stroke-[2.5]" />
      ) : (
        <ClipboardDocumentIcon className="h-4 w-4 stroke-2" />
      )}
    </BrutalIconButton>
  );
}
