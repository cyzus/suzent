import React, { useState } from 'react';
import { SettingsListAction } from './SettingsCard';

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
    <SettingsListAction
      tone={tone}
      disabled={!value}
      onClick={() => {
        if (!value) return;
        navigator.clipboard?.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? 'Copied' : label}
    </SettingsListAction>
  );
}
