import React, { useState } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { isImeComposing } from '../../lib/ime';

export const MAX_WAKE_PHRASES = 8;

const normalize = (phrase: string) => phrase.trim().replace(/\s+/g, ' ');

/** Phrases as removable chips, with an inline box that adds one on Enter. */
export function WakePhraseEditor({
  value,
  onChange,
  labelledBy,
  invalidWords = [],
}: {
  value: string[];
  onChange: (phrases: string[]) => void;
  labelledBy?: string;
  invalidWords?: string[];
}): React.ReactElement {
  const { t } = useI18n();
  const [draft, setDraft] = useState('');
  const phrases = value.filter((phrase) => phrase.trim());
  const full = phrases.length >= MAX_WAKE_PHRASES;
  const flagged = invalidWords.map((word) => word.toLowerCase());

  const commit = () => {
    const phrase = normalize(draft);
    setDraft('');
    if (!phrase || full) return;
    if (phrases.some((existing) => existing.toLowerCase() === phrase.toLowerCase())) return;
    onChange([...phrases, phrase]);
  };

  const remove = (index: number) => onChange(phrases.filter((_, i) => i !== index));

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (isImeComposing(event)) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      commit();
    } else if (event.key === 'Backspace' && !draft && phrases.length) {
      remove(phrases.length - 1);
    }
  };

  return (
    <div
      role="group"
      aria-labelledby={labelledBy}
      className="mt-1 flex min-h-[2.75rem] flex-wrap items-center gap-1.5 border-2 border-brutal-black bg-white px-2 py-1.5 focus-within:border-brutal-blue dark:bg-zinc-800"
    >
      {phrases.map((phrase, index) => {
        const bad = flagged.some((word) => phrase.toLowerCase().split(' ').includes(word));
        return (
          <span
            key={phrase}
            className={`inline-flex items-center gap-1 border-2 py-0.5 pl-2 pr-1 text-sm font-medium ${
              bad
                ? 'border-brutal-red bg-red-50 text-brutal-red dark:bg-red-950'
                : 'border-brutal-black bg-neutral-100 dark:bg-zinc-700'
            }`}
          >
            {phrase}
            <button
              type="button"
              onClick={() => remove(index)}
              aria-label={t('voice.wake.removePhrase', { phrase })}
              className="p-0.5 hover:bg-neutral-200 dark:hover:bg-zinc-600"
            >
              <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </span>
        );
      })}
      {!full && (
        <input
          aria-labelledby={labelledBy}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
          placeholder={phrases.length ? t('voice.wake.addPhrase') : t('voice.wake.firstPhrase')}
          className="min-w-[8rem] flex-1 bg-transparent px-1 py-1 text-sm font-normal placeholder:text-neutral-400 focus:outline-none"
        />
      )}
    </div>
  );
}
