import React from 'react';
import { CheckIcon } from '@heroicons/react/24/outline';

interface SettingsChoice<T extends string> {
  value: T;
  label: string;
  preview?: React.ReactNode;
}

interface SettingsChoiceGroupProps<T extends string> {
  label: string;
  value: T;
  options: readonly SettingsChoice<T>[];
  onChange: (value: T) => void;
}

export function SettingsChoiceGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: SettingsChoiceGroupProps<T>): React.ReactElement {
  return (
    <div className="flex flex-wrap gap-3" role="group" aria-label={label}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={`overflow-hidden border-2 border-brutal-black text-sm font-bold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 dark:focus-visible:outline-white ${selected ? 'bg-brutal-yellow text-brutal-black shadow-brutal-sm' : 'bg-white text-neutral-700 hover:bg-neutral-100 dark:bg-zinc-900 dark:text-neutral-200 dark:hover:bg-zinc-700'}`}
          >
            {option.preview && (
              <div className="h-24 w-36 border-b-2 border-brutal-black" aria-hidden="true">
                {option.preview}
              </div>
            )}
            <span className="flex items-center justify-center gap-2 px-3 py-2">
              <CheckIcon
                className={`h-4 w-4 shrink-0 ${selected ? '' : 'invisible'}`}
                aria-hidden="true"
              />
              {option.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
