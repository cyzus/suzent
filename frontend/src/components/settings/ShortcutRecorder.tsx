import React, { useState } from 'react';
import { BrutalButton } from '../BrutalButton';
import { useI18n } from '../../i18n';
import { isImeComposing } from '../../lib/ime';
import { acceleratorFromKeyPress, acceleratorKeycaps } from '../../lib/accelerator';
import { detectDesktopPlatform } from '../../lib/titleBarPlatform';

const isMac =
  typeof navigator !== 'undefined' &&
  detectDesktopPlatform(navigator.userAgent, navigator.platform) === 'macos';

function Keycaps({ parts }: { parts: string[] }): React.ReactElement {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {acceleratorKeycaps(parts, isMac).map((cap, index) => (
        <kbd
          key={index}
          className="inline-flex h-6 min-w-6 items-center justify-center border-2 border-brutal-black bg-neutral-100 px-1.5 font-sans text-xs font-bold leading-none dark:bg-zinc-700"
        >
          {cap}
        </kbd>
      ))}
    </span>
  );
}

/** Click, then press a key combination to set a global shortcut. */
export function ShortcutRecorder({
  value,
  onChange,
  labelledBy,
}: {
  value: string;
  onChange: (accelerator: string) => void;
  labelledBy?: string;
}): React.ReactElement {
  const { t } = useI18n();
  const [recording, setRecording] = useState(false);
  const [held, setHeld] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  const stop = () => {
    setRecording(false);
    setHeld([]);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!recording || isImeComposing(event)) return;
    event.preventDefault();
    event.stopPropagation();
    const plain = !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey;
    if (event.key === 'Escape' && plain) {
      stop();
      return;
    }
    const result = acceleratorFromKeyPress(event, isMac);
    switch (result.kind) {
      case 'partial':
        setHeld(result.modifiers);
        return;
      case 'needs_modifier':
        setProblem('voice.shortcut.needsModifier');
        return;
      case 'unsupported':
        setProblem('voice.shortcut.unsupported');
        return;
      case 'done':
        setProblem(null);
        stop();
        if (result.accelerator !== value) onChange(result.accelerator);
    }
  };

  const onKeyUp = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!recording) return;
    const result = acceleratorFromKeyPress(event, isMac);
    if (result.kind === 'partial') setHeld(result.modifiers);
  };

  return (
    <div className="mt-1 space-y-1">
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-labelledby={labelledBy}
          aria-pressed={recording}
          onClick={() => {
            setProblem(null);
            setRecording(true);
          }}
          onKeyDown={onKeyDown}
          onKeyUp={onKeyUp}
          onBlur={stop}
          className={`flex min-h-[2.75rem] flex-1 items-center border-2 bg-white px-3 py-2 text-left text-sm font-normal focus:outline-none dark:bg-zinc-800 ${
            recording
              ? 'border-brutal-blue'
              : 'border-brutal-black hover:bg-neutral-50 dark:hover:bg-zinc-700'
          }`}
        >
          {recording ? (
            held.length ? (
              <span className="inline-flex items-center gap-1">
                <Keycaps parts={held} />
                <span className="text-neutral-500">+ …</span>
              </span>
            ) : (
              <span className="text-brutal-blue">{t('voice.shortcut.pressKeys')}</span>
            )
          ) : value ? (
            <Keycaps parts={value.split('+')} />
          ) : (
            <span className="text-neutral-500 dark:text-neutral-400">
              {t('voice.shortcut.none')}
            </span>
          )}
        </button>
        {value && !recording && (
          <BrutalButton size="xs" onClick={() => onChange('')}>
            {t('voice.shortcut.clear')}
          </BrutalButton>
        )}
      </div>
      {problem && (
        <p role="status" className="text-xs text-brutal-red">
          {t(problem)}
        </p>
      )}
    </div>
  );
}
